"""Derive what a pull request's CI runs, as step scripts `scripts/preflight.sh` executes.

Not a gate: it PLANS. `preflight.sh` runs the plan in a throwaway container and
judges each step by its exit status. The set of steps is DERIVED from the
workflows, never listed by hand: every job of every workflow triggered by
`pull_request`, each `run:` step in order, with `${{ }}` expressions resolved
from a fixed table. A job is planned as one of:

    run      every step runs in the API image: a job whose `run:` text, comment
             lines aside, invokes none of pnpm, npm, npx or docker
    github   a job that needs the composed stack, a browser or the web
             toolchain (E2E, Demo, Web, Secret scan). It stays on GitHub and is
             listed so nobody reads its absence as a pass. So is a job that
             uses an action other than checkout, setup-python or an artifact
             move. `preflight.sh` runs
             the web checks (prettier, eslint, tsc, vitest) by its own route.

Inside a `run` job a step is one of:

    run       executed as GitHub does, `bash --noprofile --norc -e`, in its
              `working-directory`
    na        its `if:` excludes this author (the dependabot-only steps)
    advisory  `continue-on-error: true` in CI, so it cannot fail a build; run
              and reported, never counted

    python apps/api/scripts/preflight_plan.py --root R --out DIR \\
        --base-branch main --pr-number N --unit full|narrow [--narrow-files F]

writes DIR/steps.tsv (one row per step: INDEX KIND WORKFLOW JOB WORKDIR NAME)
and DIR/step-INDEX.sh / DIR/step-INDEX.env for every step it plans to run, then
prints the rows. The PR title and body never enter a script: the two env values
that carry them (`${{ github.event.pull_request.title }}` / `.body`) are read at
run time from files the caller provides, so untrusted text is never spliced
into shell source.

`--unit narrow` rewrites the one unit-suite step (`pytest -m unit tests/unit
...`) to the test files listed in `--narrow-files`, and adds a step right after
CI's selection gate that rewrites the certified selection to that same set, so
the run-count check that follows still holds the run to what it was told to
run. Every rewrite is announced in the step's name.

Exit 0 with the plan; 2 (could not look) when a workflow cannot be read, when an
expression, `if:`, `shell:` or action is outside the table, when the unit step
is not found exactly once in `--unit narrow`, or when nothing is planned.
"""

from __future__ import annotations

import re
import shlex
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # a host Python without PyYAML: could not look, not a finding
    sys.stderr.write("preflight-plan: COULD NOT LOOK -- PyYAML is not installed in this Python\n")
    raise SystemExit(2) from None

#: A job invoking any of these (outside a comment) cannot run in the API image.
#: `node` and `git` are not here: `preflight.sh` installs both in its container,
#: because the Python job itself runs `node` (the image-optimizer gate).
_NOT_IN_API_IMAGE = re.compile(r"(^|[\s;&|(])(pnpm|npm|npx|docker)(\s|$)", re.M)

#: Actions a `run` job may use: they set up the runner or move files, and judge
#: nothing. Any other action is a step this planner cannot reproduce.
_SETUP_ACTIONS = (
    "actions/checkout@",
    "actions/setup-python@",
    "actions/upload-artifact@",
    "actions/download-artifact@",
)

#: An expression reading another job: `${{ needs.<job>.result }}` and the like.
_NEEDS_EXPR = re.compile(r"\$\{\{[^}]*\bneeds\.")
_EXPR = re.compile(r"\$\{\{\s*(.*?)\s*\}\}")
_BOT = "github.event.pull_request.user.login == 'dependabot[bot]'"
_NOT_BOT = "github.event.pull_request.user.login != 'dependabot[bot]'"
_RUN_IFS = {"always()", "success()", _NOT_BOT}

#: Env values that carry untrusted PR text: never spliced, read from a file.
_FROM_FILE = {
    "github.event.pull_request.title": "PREFLIGHT_TITLE_FILE",
    "github.event.pull_request.body": "PREFLIGHT_BODY_FILE",
}

#: The close guard's `--linked FILE`, GitHub's own answer about what a PR closes.
_LINKED = re.compile(r"[ \t]*(\\\n[ \t]*)?--linked[ \t]+\S+")

UNIT_STEP = re.compile(r"^pytest -m unit tests/unit(\s|$)")


class CouldNotLook(Exception):
    pass


def triggers(data: dict) -> set[str]:
    # YAML 1.1 reads the bare key `on` as the boolean True.
    on = data.get("on", data.get(True))
    if isinstance(on, str):
        return {on}
    if isinstance(on, (list, dict)):
        return {str(t) for t in on}
    return set()


def _values(base_branch: str, pr_number: str) -> dict[str, str]:
    return {
        "github.base_ref": base_branch,
        "github.event.pull_request.number": pr_number,
        "github.token": "preflight-has-no-token",
        "runner.temp": "$RUNNER_TEMP",
        "github.workspace": "$GITHUB_WORKSPACE",
    }


def resolve(text: str, values: dict[str, str], where: str) -> str:
    """Substitute every `${{ }}` from `values`; anything else is could-not-look."""

    def one(match: re.Match) -> str:
        expr = match.group(1)
        if expr not in values:
            raise CouldNotLook(f"{where}: no value for the expression ${{{{ {expr} }}}}")
        return values[expr]

    return _EXPR.sub(one, text)


def _job_runs_here(job: dict) -> bool:
    """Every step a setup action or a `run:` using only what the API image has,
    and nothing in the job reading another job's outcome.

    A job that reads `needs.<job>.result` (an aggregate, #680) judges OTHER
    jobs, which exist only on GitHub. It stays there and is listed, rather than
    being run with a value the planner would have to guess (#736 6217409672).
    """
    if _NEEDS_EXPR.search(yaml.safe_dump(job)):
        return False
    steps = job.get("steps") or []
    if any(
        s.get("uses") is not None and not str(s["uses"]).startswith(_SETUP_ACTIONS) for s in steps
    ):
        return False
    lines = (ln for s in steps for ln in str(s.get("run", "")).splitlines())
    text = "\n".join(ln for ln in lines if not ln.lstrip().startswith("#"))
    return bool(text.strip()) and not _NOT_IN_API_IMAGE.search(text)


def _step_kind(step: dict, where: str) -> str:
    cond = step.get("if")
    if cond is not None:
        cond = str(cond).strip()
        if cond == _BOT:
            return "na"
        if cond not in _RUN_IFS:
            raise CouldNotLook(f"{where}: an `if:` this planner does not understand: {cond!r}")
    if step.get("continue-on-error"):
        return "advisory"
    return "run"


def _env_lines(env: dict, values: dict[str, str], where: str) -> list[str]:
    lines = []
    for key, raw in (env or {}).items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(key)):
            raise CouldNotLook(f"{where}: env name {key!r} is not a shell name")
        raw = str(raw)
        whole = _EXPR.fullmatch(raw.strip())
        if whole and whole.group(1) in _FROM_FILE:
            lines.append(f'export {key}="$(cat "${_FROM_FILE[whole.group(1)]}")"')
            continue
        lines.append(f"export {key}={shlex.quote(resolve(raw, values, where))}")
    return lines


def plan(root: Path, base_branch: str, pr_number: str, unit: str, narrow: list[str]) -> list[dict]:
    """Every step of every pull-request job, in order, with what to run."""
    values = _values(base_branch, pr_number)
    workflows = sorted(p for p in (root / ".github" / "workflows").glob("*.y*ml") if p.is_file())
    if not workflows:
        raise CouldNotLook(f"no workflows under {root / '.github' / 'workflows'}")
    steps: list[dict] = []
    unit_steps = 0
    for path in workflows:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
            raise CouldNotLook(f"cannot read {path.name}: {exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("jobs"), dict):
            raise CouldNotLook(f"{path.name} has no jobs mapping")
        if "pull_request" not in triggers(data):
            continue
        # Settings that change what every step sees: refused, never ignored.
        for key in ("env", "defaults"):
            if data.get(key):
                raise CouldNotLook(f"{path.name}: workflow-level `{key}:` is not reproduced here")
        for job_id, job in data["jobs"].items():
            name = str(job.get("name", job_id))
            for key in ("container", "services"):
                if job.get(key) and _job_runs_here(job):
                    raise CouldNotLook(f"{path.name} {job_id}: job `{key}:` is not reproduced here")
            if ((job.get("defaults") or {}).get("run") or {}).get("shell") is not None:
                raise CouldNotLook(
                    f"{path.name} {job_id}: job `defaults.run.shell` is not reproduced here"
                )
            if not _job_runs_here(job):
                steps.append(
                    {
                        "kind": "github",
                        "workflow": path.name,
                        "job": job_id,
                        "wd": "-",
                        "name": name,
                    }
                )
                continue
            if job.get("if") is not None and str(job["if"]).strip() not in _RUN_IFS:
                raise CouldNotLook(
                    f"{path.name} {job_id}: a job `if:` this planner does not understand"
                )
            default_wd = ((job.get("defaults") or {}).get("run") or {}).get(
                "working-directory", "."
            )
            job_env = job.get("env") or {}
            for n, step in enumerate(job.get("steps") or []):
                where = f"{path.name} {job_id} step {n}"
                uses = step.get("uses")
                if uses is not None:
                    if not str(uses).startswith(_SETUP_ACTIONS):
                        raise CouldNotLook(
                            f"{where}: uses an action this planner cannot reproduce: {uses}"
                        )
                    continue
                run = step.get("run")
                if not isinstance(run, str):
                    raise CouldNotLook(f"{where}: neither `uses` nor a `run` string")
                shell = step.get("shell")
                if shell is not None and str(shell) not in ("bash", "bash -e {0}"):
                    raise CouldNotLook(f"{where}: shell {shell!r} is not the bash GitHub runs")
                label = str(step.get("name") or run.strip().splitlines()[0])
                kind = _step_kind(step, where)
                wd = str(step.get("working-directory", default_wd))
                if kind == "na":
                    # Excluded for this author: listed, never resolved or run.
                    steps.append(
                        {
                            "kind": kind,
                            "workflow": path.name,
                            "job": job_id,
                            "wd": wd,
                            "name": label,
                        }
                    )
                    continue
                script = resolve(run, values, where)
                # GitHub runs an EXPLICIT `shell: bash` as `bash -eo pipefail`,
                # the default as `bash -e`; the runner reads this marker.
                pipefail = shell is not None and str(shell) == "bash"
                if pr_number == "0" and "--linked" in script:
                    # Before a PR exists GitHub links nothing, and an empty set
                    # would read as "verified: closes nothing". The flag is
                    # dropped and the step says so; the prose check still runs.
                    script = _LINKED.sub("", script)
                    if "--linked" in script:
                        # A respelling (`--linked=FILE`) the pattern missed would
                        # run against an empty set and print "verified".
                        raise CouldNotLook(f"{where}: a --linked this planner cannot remove")
                    label += " [NO PR: --linked dropped, GitHub's linked set NOT verified]"
                if unit == "narrow" and UNIT_STEP.match(script.strip()):
                    unit_steps += 1
                    rest = UNIT_STEP.sub("", script.strip(), count=1)
                    script = (
                        " ".join(["pytest -m unit", *map(shlex.quote, narrow), rest]).rstrip()
                        + "\n"
                    )
                    label += " [NARROWED by preflight --unit narrow]"
                elif unit == "full" and UNIT_STEP.match(script.strip()):
                    unit_steps += 1
                env = _env_lines({**job_env, **(step.get("env") or {})}, values, where)
                steps.append(
                    {
                        "kind": kind,
                        "workflow": path.name,
                        "job": job_id,
                        "wd": wd,
                        "name": label,
                        "script": ("set -o pipefail\n" if pipefail else "") + script,
                        "env": env,
                    }
                )
                if (
                    unit == "narrow"
                    and "--selected-out" in script
                    and "check_ci_selection" in script
                ):
                    out = re.search(r'--selected-out\s+("[^"]+"|\S+)', script).group(1)
                    files = " ".join(map(shlex.quote, narrow))
                    steps.append(
                        {
                            "kind": "run",
                            "workflow": path.name,
                            "job": job_id,
                            "wd": wd,
                            "name": "the certified selection, NARROWED by preflight to the same files as the run",
                            "script": (
                                f"python -m pytest --collect-only -q -p no:cacheprovider -m unit {files}"
                                f' | grep "::" > {out}\n'
                                f'test -s {out}\necho "narrowed selection: $(wc -l < {out}) test(s)"\n'
                            ),
                            "env": env,
                        }
                    )
    if unit_steps != 1:
        raise CouldNotLook(
            f"expected exactly one unit-suite step (`pytest -m unit tests/unit`), found {unit_steps}"
        )
    if not any(s["kind"] == "run" for s in steps):
        raise CouldNotLook("no step to run in any pull-request workflow")
    return steps


def _parse(argv: list[str]) -> dict[str, str]:
    opts: dict[str, str] = {}
    it = iter(argv)
    for arg in it:
        if arg not in (
            "--root",
            "--out",
            "--base-branch",
            "--pr-number",
            "--unit",
            "--narrow-files",
        ):
            raise CouldNotLook(f"unknown argument {arg!r}")
        value = next(it, None)
        if not value:
            raise CouldNotLook(f"{arg} given with no value")
        opts[arg] = value
    for need in ("--root", "--out", "--base-branch", "--pr-number", "--unit"):
        if need not in opts:
            raise CouldNotLook(f"missing {need}")
    if opts["--unit"] not in ("full", "narrow"):
        raise CouldNotLook("--unit must be full or narrow")
    if not re.fullmatch(r"[0-9]+", opts["--pr-number"]):
        raise CouldNotLook("--pr-number must be digits (0 before the PR exists)")
    if (opts["--unit"] == "narrow") != ("--narrow-files" in opts):
        raise CouldNotLook("--narrow-files goes with --unit narrow, and only with it")
    return opts


def main(argv: list[str]) -> int:
    try:
        opts = _parse(argv)
        narrow: list[str] = []
        if opts["--unit"] == "narrow":
            narrow = [
                ln.strip()
                for ln in Path(opts["--narrow-files"]).read_text(encoding="utf-8").splitlines()
                if ln.strip()
            ]
            if not narrow:
                raise CouldNotLook("--unit narrow with no test files: nothing would run")
        steps = plan(
            Path(opts["--root"]), opts["--base-branch"], opts["--pr-number"], opts["--unit"], narrow
        )
    except (CouldNotLook, OSError) as exc:
        print(f"preflight-plan: COULD NOT LOOK -- {exc}", file=sys.stderr)
        return 2
    out = Path(opts["--out"])
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, step in enumerate(steps, 1):
        rows.append(
            "\t".join(
                [
                    f"{i:03d}",
                    step["kind"],
                    step["workflow"],
                    step["job"],
                    step["wd"],
                    step["name"].replace("\t", " ").replace("\n", " "),
                ]
            )
        )
        if "script" in step:
            (out / f"step-{i:03d}.sh").write_bytes(step["script"].encode("utf-8"))
            (out / f"step-{i:03d}.env").write_bytes(("\n".join(step["env"]) + "\n").encode("utf-8"))
    (out / "steps.tsv").write_bytes(("\n".join(rows) + "\n").encode("utf-8"))
    for row in rows:
        print(row)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (SystemExit, KeyboardInterrupt):
        raise
    except BaseException as exc:  # noqa: BLE001 - deliberate: a crash is not a plan
        sys.stderr.write(f"preflight-plan: CRASHED: {type(exc).__name__}: {exc}\n")
        raise SystemExit(2) from exc
