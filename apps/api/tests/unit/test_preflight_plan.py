"""`preflight_plan.py` derives what `scripts/preflight.sh` runs from the workflows.

The expected values come from the SPEC (#736, 6204543223 item 4): every CI step
the API image can run is planned, in order; E2E and Demo stay on GitHub; the
drafted PR title and body are checked; a step or expression the planner cannot
reproduce is could-not-look, never a shorter plan.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import scripts.preflight_plan as pp

from tests._paths import find_workflows_dir

pytestmark = pytest.mark.unit


def _skip_without_workflows() -> None:
    # The api container mounts only apps/api. On a full checkout (CI) this
    # cannot fire: ci.yml's "the audit-gate tests must not skip on a full
    # checkout" step fails if find_workflows_dir returns None there.
    pytest.skip("no .github/workflows above this file (the api container mounts apps/api)")


def _repo(tmp_path: Path, **workflows: str) -> Path:
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    for name, body in workflows.items():
        (wf / name).write_text(textwrap.dedent(body), encoding="utf-8")
    return tmp_path


UNIT = "      - run: pytest -m unit tests/unit\n"

CI = """\
    on:
      pull_request:
    jobs:
      python:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v7
          - name: install
            working-directory: apps/api
            run: pip install -e ".[dev]"
          - name: gate
            working-directory: apps/api
            run: python -m scripts.check_ci_selection --selected-out "$RUNNER_TEMP/sel.txt"
          - name: unit
            working-directory: apps/api
            run: pytest -m unit tests/unit -n 4
          - name: advisory one
            continue-on-error: true
            run: pip-audit
          - name: bot only
            if: github.event.pull_request.user.login == 'dependabot[bot]'
            run: echo ${{ github.event.pull_request.user.login }}
          - name: human only
            if: github.event.pull_request.user.login != 'dependabot[bot]'
            # node and docker in a comment do not count
            run: |
              # docker compose up
              python -m scripts.check_issue_references --range "origin/${{ github.base_ref }}..HEAD"
      web:
        runs-on: ubuntu-latest
        steps:
          - run: pnpm -F web lint
      scan:
        runs-on: ubuntu-latest
        steps:
          - uses: gitleaks/gitleaks-action@v3
      e2e:
        runs-on: ubuntu-latest
        steps:
          - run: docker compose up -d
"""


def _plan(root: Path, unit: str = "full", narrow: list[str] | None = None) -> list[dict]:
    return pp.plan(root, "main", "0", unit, narrow or [])


def _by_name(steps: list[dict]) -> dict[str, dict]:
    return {s["name"]: s for s in steps}


def test_every_runnable_step_is_planned_in_order_with_its_kind(tmp_path: Path) -> None:
    steps = _plan(_repo(tmp_path, **{"ci.yml": CI}))
    python = [s for s in steps if s["job"] == "python"]
    # From CI above: the checkout is setup, every run step is planned, in order.
    assert [s["name"] for s in python] == [
        "install",
        "gate",
        "unit",
        "advisory one",
        "bot only",
        "human only",
    ]
    assert [s["kind"] for s in python] == ["run", "run", "run", "advisory", "na", "run"]
    assert "script" not in _by_name(python)["bot only"], "an excluded step is never resolved or run"
    assert _by_name(python)["gate"]["wd"] == "apps/api"


def test_jobs_the_api_image_cannot_run_stay_on_github(tmp_path: Path) -> None:
    steps = _plan(_repo(tmp_path, **{"ci.yml": CI}))
    kinds = {s["job"]: s["kind"] for s in steps if s["job"] != "python"}
    assert kinds == {"web": "github", "scan": "github", "e2e": "github"}


def test_expressions_resolve_from_the_table(tmp_path: Path) -> None:
    steps = _by_name(_plan(_repo(tmp_path, **{"ci.yml": CI})))
    assert 'origin/main..HEAD"' in steps["human only"]["script"]
    assert "${{" not in steps["human only"]["script"]


@pytest.mark.parametrize(
    ("body", "why"),
    [
        ("      - run: echo ${{ secrets.ANTHROPIC_API_KEY }}\n", "no value for the expression"),
        ("      - if: github.event_name == 'push'\n        run: echo hi\n", "does not understand"),
        ("      - uses: some/other-action@v1\n        with: {x: 1}\n      - run: echo\n", None),
        ("      - shell: pwsh\n        run: echo hi\n", "is not the bash GitHub runs"),
    ],
    ids=["unknown-expression", "unknown-if", "unknown-action", "other-shell"],
)
def test_what_the_planner_cannot_reproduce_is_could_not_look(
    tmp_path: Path, body: str, why: str | None
) -> None:
    wf = "on: [pull_request]\njobs:\n  j:\n    runs-on: ubuntu-latest\n    steps:\n" + UNIT + body
    root = _repo(tmp_path, **{"ci.yml": wf})
    if why is None:
        # An unknown action makes the whole job GitHub-only -- and then there
        # is no unit step left to plan, which is could-not-look too.
        with pytest.raises(pp.CouldNotLook, match="exactly one unit-suite step"):
            _plan(root)
        return
    with pytest.raises(pp.CouldNotLook, match=why):
        _plan(root)


def test_pr_text_never_enters_a_script(tmp_path: Path) -> None:
    wf = """\
        on: pull_request
        jobs:
          j:
            runs-on: ubuntu-latest
            steps:
              - run: pytest -m unit tests/unit
              - name: body
                env:
                  PR_BODY: ${{ github.event.pull_request.body }}
                  PR_TITLE: ${{ github.event.pull_request.title }}
                run: printf '%s' "$PR_BODY" > /tmp/body.md
    """
    step = _by_name(_plan(_repo(tmp_path, **{"ci.yml": wf})))["body"]
    assert 'export PR_BODY="$(cat "$PREFLIGHT_BODY_FILE")"' in step["env"]
    assert 'export PR_TITLE="$(cat "$PREFLIGHT_TITLE_FILE")"' in step["env"]
    # Inline, the same expression is refused: it would splice untrusted text.
    inline = wf.replace(
        """printf '%s' "$PR_BODY" """, "echo ${{ github.event.pull_request.body }} "
    )
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(
        textwrap.dedent(inline), encoding="utf-8"
    )
    with pytest.raises(pp.CouldNotLook, match="no value for the expression"):
        _plan(tmp_path)


def test_narrow_rewrites_the_unit_step_and_the_certified_selection(tmp_path: Path) -> None:
    steps = _plan(
        _repo(tmp_path, **{"ci.yml": CI}),
        "narrow",
        ["tests/unit/test_a.py", "tests/unit/test_b.py"],
    )
    python = [s for s in steps if s["job"] == "python"]
    names = [s["name"] for s in python]
    # The narrowed selection comes IMMEDIATELY after CI's gate, before the run.
    gate_at = names.index("gate")
    assert "NARROWED by preflight" in names[gate_at + 1]
    assert "sel.txt" in python[gate_at + 1]["script"]
    assert "tests/unit/test_a.py tests/unit/test_b.py" in python[gate_at + 1]["script"]
    unit = python[gate_at + 2]
    assert unit["name"] == "unit [NARROWED by preflight --unit narrow]"
    assert unit["script"].strip() == "pytest -m unit tests/unit/test_a.py tests/unit/test_b.py -n 4"


def test_full_leaves_the_unit_step_exactly_as_ci_runs_it(tmp_path: Path) -> None:
    unit = _by_name(_plan(_repo(tmp_path, **{"ci.yml": CI})))["unit"]
    assert unit["script"].strip() == "pytest -m unit tests/unit -n 4"


@pytest.mark.parametrize("copies", [0, 2])
def test_the_unit_step_must_be_found_exactly_once(tmp_path: Path, copies: int) -> None:
    wf = (
        "on: [pull_request]\njobs:\n  j:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n"
        + UNIT * copies
    )
    with pytest.raises(pp.CouldNotLook, match="exactly one unit-suite step"):
        _plan(_repo(tmp_path, **{"ci.yml": wf}))


def test_workflows_not_run_on_pull_requests_are_not_planned(tmp_path: Path) -> None:
    sched = "on:\n  schedule:\n    - cron: '0 0 * * *'\njobs:\n  s:\n    runs-on: ubuntu-latest\n    steps:\n      - run: python sweep.py\n"
    steps = _plan(_repo(tmp_path, **{"ci.yml": CI, "sweep.yml": sched}))
    assert {s["workflow"] for s in steps} == {"ci.yml"}


def test_the_real_workflows_plan_the_python_and_audit_jobs_and_keep_e2e_on_github() -> None:
    wf = find_workflows_dir(Path(__file__).resolve())
    if wf is None:
        _skip_without_workflows()
    steps = pp.plan(wf.parent.parent, "main", "0", "full", [])
    jobs: dict[tuple[str, str], set[str]] = {}
    for s in steps:
        jobs.setdefault((s["workflow"], s["job"]), set()).add(s["kind"])
    # The spec: E2E and Demo stay on GitHub. The web job needs pnpm.
    for job in ("e2e", "demo", "web", "secret-scan"):
        assert jobs[("ci.yml", job)] == {"github"}, job
    assert "github" not in jobs[("ci.yml", "python")]
    audit = [k for (w, _), k in jobs.items() if w == "audit-gate.yml"]
    assert audit and all("github" not in k for k in audit)


def test_main_writes_a_script_per_planned_step_and_nothing_for_the_rest(
    tmp_path: Path, capsys
) -> None:
    root = _repo(tmp_path / "r", **{"ci.yml": CI})
    out = tmp_path / "plan"
    code = pp.main(
        [
            "--root",
            str(root),
            "--out",
            str(out),
            "--base-branch",
            "main",
            "--pr-number",
            "0",
            "--unit",
            "full",
        ]
    )
    assert code == 0, capsys.readouterr().err
    rows = (out / "steps.tsv").read_text(encoding="utf-8").splitlines()
    scripts = sorted(p.name for p in out.glob("step-*.sh"))
    planned = [r.split("\t")[0] for r in rows if r.split("\t")[1] in ("run", "advisory")]
    assert scripts == [f"step-{i}.sh" for i in planned]


@pytest.mark.parametrize(
    "argv",
    [
        [],
        [
            "--root",
            ".",
            "--out",
            "o",
            "--base-branch",
            "main",
            "--pr-number",
            "x",
            "--unit",
            "full",
        ],
        [
            "--root",
            ".",
            "--out",
            "o",
            "--base-branch",
            "main",
            "--pr-number",
            "0",
            "--unit",
            "some",
        ],
        [
            "--root",
            ".",
            "--out",
            "o",
            "--base-branch",
            "main",
            "--pr-number",
            "0",
            "--unit",
            "narrow",
        ],
        [
            "--root",
            ".",
            "--out",
            "o",
            "--base-branch",
            "main",
            "--pr-number",
            "0",
            "--unit",
            "full",
            "--bogus",
            "1",
        ],
    ],
    ids=["empty", "pr-not-digits", "unit-unknown", "narrow-without-files", "unknown-flag"],
)
def test_bad_usage_is_could_not_look(argv: list[str], capsys) -> None:
    assert pp.main(argv) == 2
    assert "COULD NOT LOOK" in capsys.readouterr().err


# RAW, so the backslash continuations reach the planner as the workflow has them
# (review of d4ace8ef: a plain string folded them away, and the pattern's
# continuation branch was never exercised).
GUARD = r"""    on: pull_request
    jobs:
      j:
        runs-on: ubuntu-latest
        steps:
          - run: pytest -m unit tests/unit
          - name: close guard
            run: |
              python -m scripts.check_issue_references \
                --title /tmp/t.txt \
                --linked /tmp/pr_linked.txt
"""


def test_before_a_pr_exists_the_close_guard_runs_without_linked_and_says_so(tmp_path: Path) -> None:
    root = _repo(tmp_path, **{"ci.yml": GUARD})
    step = _by_name(pp.plan(root, "main", "0", "full", []))
    (name,) = [n for n in step if n.startswith("close guard")]
    assert "NOT verified" in name
    assert "--linked" not in step[name]["script"]
    # The continuation before --linked goes with it: no dangling backslash.
    assert step[name]["script"].rstrip().endswith("--title /tmp/t.txt"), step[name]["script"]


def test_the_real_close_guard_step_loses_linked_and_nothing_else() -> None:
    wf = find_workflows_dir(Path(__file__).resolve())
    if wf is None:
        _skip_without_workflows()
    without = [
        s for s in pp.plan(wf.parent.parent, "main", "0", "full", []) if "NOT verified" in s["name"]
    ]
    with_pr = {s["name"]: s for s in pp.plan(wf.parent.parent, "main", "5", "full", [])}
    assert len(without) == 1, [s["name"] for s in without]
    step = without[0]
    original = with_pr[step["name"].split(" [NO PR")[0]]["script"]
    assert "--linked /tmp/pr_linked.txt" in original
    assert "--linked" not in step["script"]
    assert not step["script"].rstrip().endswith("\\"), step["script"]
    # Everything else in the command is untouched.
    assert [ln.strip(" \\") for ln in original.splitlines() if "--linked" not in ln] == [
        ln.strip(" \\") for ln in step["script"].splitlines()
    ]


def test_a_linked_the_pattern_cannot_remove_is_could_not_look(tmp_path: Path) -> None:
    root = _repo(tmp_path, **{"ci.yml": GUARD.replace("--linked /tmp", "--linked=/tmp")})
    with pytest.raises(pp.CouldNotLook, match="a --linked this planner cannot remove"):
        pp.plan(root, "main", "0", "full", [])


def test_with_a_pr_the_close_guard_keeps_linked(tmp_path: Path) -> None:
    root = _repo(tmp_path, **{"ci.yml": GUARD})
    step = _by_name(pp.plan(root, "main", "1189", "full", []))
    assert "--linked /tmp/pr_linked.txt" in step["close guard"]["script"]


def test_an_explicit_bash_shell_runs_with_pipefail_as_github_does(tmp_path: Path) -> None:
    wf = "on: pull_request\njobs:\n  j:\n    runs-on: ubuntu-latest\n    steps:\n" + UNIT
    wf += "      - name: explicit\n        shell: bash\n        run: a | b\n"
    wf += "      - name: default\n        run: a | b\n"
    steps = _by_name(_plan(_repo(tmp_path, **{"ci.yml": wf})))
    assert steps["explicit"]["script"].startswith("set -o pipefail\n")
    assert "pipefail" not in steps["default"]["script"]


@pytest.mark.parametrize(
    ("snippet", "why"),
    [
        ("env:\n  X: 1\n", "workflow-level `env:`"),
        ("defaults:\n  run:\n    shell: sh\n", "workflow-level `defaults:`"),
    ],
    ids=["workflow-env", "workflow-defaults"],
)
def test_workflow_settings_that_reach_every_step_are_refused(
    tmp_path: Path, snippet: str, why: str
) -> None:
    wf = snippet + "on: pull_request\njobs:\n  j:\n    runs-on: ubuntu-latest\n    steps:\n" + UNIT
    with pytest.raises(pp.CouldNotLook, match=why):
        _plan(_repo(tmp_path, **{"ci.yml": wf}))


@pytest.mark.parametrize("key", ["services", "container"])
def test_a_local_job_with_services_or_a_container_is_refused(tmp_path: Path, key: str) -> None:
    wf = (
        f"on: pull_request\njobs:\n  j:\n    runs-on: ubuntu-latest\n    {key}:\n      x: y\n    steps:\n"
        + UNIT
    )
    with pytest.raises(pp.CouldNotLook, match=f"job `{key}:`"):
        _plan(_repo(tmp_path, **{"ci.yml": wf}))
