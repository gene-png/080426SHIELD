"""Derive the gates a pull request's CI runs, for `scripts/preflight.sh`.

Not a gate itself: it PLANS, and `preflight.sh` runs the plan. It prints one
tab-separated row per gate invocation found in a pull-request-triggered
workflow:

    KIND  STEM  WORKFLOW  JOB  WORKING-DIRECTORY  COMMAND

KIND is how preflight treats the row:

    run       verbatim: no `${{ }}`, no `/tmp`, no shell variable -- run the
              command as written, in its working directory
    adapt     needs CI-only input (the PR body, a base ref, a temp file);
              preflight must hold an adapter for STEM or it fails
    github    in a job that needs the running stack (E2E, Demo); stays on
              GitHub, listed so nobody reads its absence as a pass
    na        the step's `if:` excludes a non-bot author (dependabot-only)
    advisory  `continue-on-error` in CI, so it cannot fail a build

THE SELECTION IS CLAUDE.md's GREP, applied to parsed `run:` text. The regex
below is the one `CLAUDE.md` publishes under condition 5 ("does any WORKFLOW
execute it as a gate"); preflight also runs that grep literally and requires
the two counts to agree, so a parse that misses a spelling the grep sees is a
could-not-look rather than a shorter list.

Exit 0 with the rows; 2 when a workflow cannot be read or parsed, when an
`if:` it does not understand guards a gate, when a job it treats as
GitHub-only is missing, or when nothing is found at all.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

GATE_RE = re.compile(
    r"(bash|python( -m)?) +[A-Za-z0-9_./-]*(check_|leave_row_oracle|tests[/.]gates|scripts[/.])"
)

#: Jobs that run against the running stack. "E2E and Demo stay on GitHub" is the
#: spec; named rather than inferred, and checked to EXIST so a rename fails loudly.
GITHUB_ONLY_JOBS = {"ci.yml": ("e2e", "demo")}

_BOT_ONLY = "github.event.pull_request.user.login == 'dependabot[bot]'"
_NOT_BOT = "github.event.pull_request.user.login != 'dependabot[bot]'"
_TOKEN_RE = re.compile(r"(?:python(?: -m)?|bash) +([A-Za-z0-9_./-]+)")


def fail(message: str) -> None:
    print(f"preflight-plan: COULD NOT LOOK -- {message}", file=sys.stderr)
    raise SystemExit(2)


def triggers(data: dict) -> set[str]:
    # YAML 1.1 reads the bare key `on` as the boolean True.
    on = data.get("on", data.get(True))
    if isinstance(on, str):
        return {on}
    if isinstance(on, (list, dict)):
        return {str(t) for t in on}
    return set()


def logical_lines(run: str) -> list[str]:
    """`run:` text as commands: continuations joined, full-line comments dropped."""
    joined = re.sub(r"\\\n\s*", " ", run)
    return [ln.strip() for ln in joined.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


def stem_of(command: str) -> str:
    match = _TOKEN_RE.match(command, GATE_RE.search(command).start())
    if match is None:
        fail(f"cannot name the gate in: {command}")
    token = match.group(1)
    if "/" in token or token.endswith((".py", ".sh")):
        return Path(token).stem
    return token.rsplit(".", 1)[-1]


def kind_of(command: str, step: dict, job: dict, job_id: str, workflow: str) -> str:
    if job_id in GITHUB_ONLY_JOBS.get(workflow, ()):
        return "github"
    if step.get("continue-on-error") or job.get("continue-on-error"):
        return "advisory"
    for condition in (step.get("if"), job.get("if")):
        if condition is None or condition == _NOT_BOT:
            continue
        if condition == _BOT_ONLY:
            return "na"
        fail(f"{workflow} job {job_id}: a gate is guarded by an `if:` this planner does not understand: {condition!r}")
    if "${{" in command or "/tmp/" in command or "$" in command:
        return "adapt"
    return "run"


def plan(root: Path) -> list[tuple[str, ...]]:
    workflows = sorted(p for p in (root / ".github" / "workflows").glob("*.y*ml") if p.is_file())
    if not workflows:
        fail(f"no workflows under {root / '.github' / 'workflows'}")
    rows: list[tuple[str, ...]] = []
    for path in workflows:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
            fail(f"cannot read {path.name}: {exc}")
        if not isinstance(data, dict) or not isinstance(data.get("jobs"), dict):
            fail(f"{path.name} has no jobs mapping")
        for job_id in GITHUB_ONLY_JOBS.get(path.name, ()):
            if job_id not in data["jobs"]:
                fail(f"{path.name} has no job '{job_id}', which this planner keeps on GitHub")
        if not triggers(data) & {"pull_request", "pull_request_target"}:
            continue
        for job_id, job in data["jobs"].items():
            default_wd = ((job.get("defaults") or {}).get("run") or {}).get("working-directory", ".")
            for step in job.get("steps") or []:
                run = step.get("run")
                if not isinstance(run, str):
                    continue
                for command in logical_lines(run):
                    if not GATE_RE.search(command):
                        continue
                    wd = step.get("working-directory", default_wd)
                    rows.append(
                        (kind_of(command, step, job, job_id, path.name), stem_of(command), path.name, job_id, wd, command)
                    )
    if not rows:
        fail("no gate invocation found in any pull-request workflow")
    return rows


def main(argv: list[str]) -> int:
    if len(argv) != 1 or not argv[0] or argv[0].startswith("-"):
        print("FAIL: usage: preflight_plan.py <repo-root>", file=sys.stderr)
        return 2
    root = Path(argv[0])
    for row in plan(root):
        print("\t".join(row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
