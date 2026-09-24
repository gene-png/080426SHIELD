"""The e2e env-gate check (#540, Playwright half): a spec gated on a variable
no workflow sets never runs in CI.

#483 is the instance: `E2E_PERF` and `E2E_OIDC` gate `test.skip(...)` in two
specs, one of them a smoke spec, and no workflow step sets either, so both
specs have self-skipped on every CI run. Written BEFORE the check.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

# The DOTTED form, deliberately: see test_leave_row_oracle_anchors.py for why a
# bare `from scripts import ...` sorts differently in the container and in CI.
import scripts.check_e2e_env_gates as gate

pytestmark = pytest.mark.unit


def _repo(tmp_path: Path, specs: dict[str, str], workflow: str, exemptions: dict) -> Path:
    for rel, body in specs.items():
        p = tmp_path / "e2e" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(body), encoding="utf-8")
    wf = tmp_path / ".github" / "workflows" / "ci.yml"
    wf.parent.mkdir(parents=True, exist_ok=True)
    wf.write_text(textwrap.dedent(workflow), encoding="utf-8")
    (tmp_path / ".github" / "e2e-env-gate-exemptions.json").write_text(
        json.dumps(exemptions), encoding="utf-8"
    )
    return tmp_path


GATED = """
    const ON = process.env.E2E_PERF === "1";
    test("x", () => { test.skip(!ON, "set E2E_PERF=1"); });
"""
SET_WORKFLOW = """
    jobs:
      e2e:
        steps:
          - name: run
            env:
              E2E_PERF: "1"
            run: npx playwright test
"""
UNSET_WORKFLOW = """
    jobs:
      e2e:
        steps:
          - run: npx playwright test
"""


def _run(root: Path, capsys) -> tuple[int, str]:
    code = gate.main(["gate", "--root", str(root)])
    return code, capsys.readouterr().out


def test_a_gate_no_workflow_sets_is_a_finding_naming_spec_and_variable(tmp_path, capsys) -> None:
    code, out = _run(_repo(tmp_path, {"perf.spec.ts": GATED}, UNSET_WORKFLOW, {}), capsys)
    assert code == 1, out
    assert "E2E_PERF" in out and "perf.spec.ts" in out, out


def test_a_gate_a_workflow_sets_is_clean(tmp_path, capsys) -> None:
    code, out = _run(_repo(tmp_path, {"perf.spec.ts": GATED}, SET_WORKFLOW, {}), capsys)
    assert code == 0, out


def test_an_exempted_gate_passes_and_is_printed_with_its_reason(tmp_path, capsys) -> None:
    root = _repo(
        tmp_path, {"perf.spec.ts": GATED}, UNSET_WORKFLOW, {"E2E_PERF": {"reason": "#483"}}
    )
    code, out = _run(root, capsys)
    assert code == 0, out
    assert "E2E_PERF" in out and "#483" in out, out


def test_an_exemption_for_a_variable_now_set_is_stale(tmp_path, capsys) -> None:
    root = _repo(tmp_path, {"perf.spec.ts": GATED}, SET_WORKFLOW, {"E2E_PERF": {"reason": "#483"}})
    code, out = _run(root, capsys)
    assert code == 1, out
    assert "stale" in out.lower(), out


def test_an_exemption_no_spec_uses_is_stale(tmp_path, capsys) -> None:
    root = _repo(tmp_path, {"perf.spec.ts": GATED}, SET_WORKFLOW, {"E2E_GONE": {"reason": "old"}})
    code, out = _run(root, capsys)
    assert code == 1, out


def test_a_spec_with_no_skip_is_not_scanned(tmp_path, capsys) -> None:
    ungated = 'const base = process.env.E2E_BASE_URL ?? "x";\ntest("y", () => {});\n'
    code, out = _run(_repo(tmp_path, {"plain.spec.ts": ungated}, UNSET_WORKFLOW, {}), capsys)
    assert code == 0, out


def test_node_modules_is_not_scanned(tmp_path, capsys) -> None:
    root = _repo(tmp_path, {"ok.spec.ts": 'test("y", () => {});\n'}, UNSET_WORKFLOW, {})
    nm = root / "e2e" / "node_modules" / "pkg" / "x.spec.ts"
    nm.parent.mkdir(parents=True)
    nm.write_text(GATED, encoding="utf-8")
    code, out = _run(root, capsys)
    assert code == 0, out


def test_an_exemption_without_a_reason_is_refused(tmp_path, capsys) -> None:
    root = _repo(tmp_path, {"perf.spec.ts": GATED}, UNSET_WORKFLOW, {"E2E_PERF": {"reason": " "}})
    code, out = _run(root, capsys)
    assert code == 2, out


def test_no_specs_is_could_not_look(tmp_path, capsys) -> None:
    root = _repo(tmp_path, {}, UNSET_WORKFLOW, {})
    (root / "e2e").mkdir(exist_ok=True)
    code, out = _run(root, capsys)
    assert code == 2, out


def test_the_wrong_directory_is_could_not_look(tmp_path, capsys) -> None:
    code, out = _run(tmp_path, capsys)
    assert code == 2, out


def test_an_unknown_argument_is_could_not_look(capsys) -> None:
    assert gate.main(["gate", "--rot", "."]) == 2


def test_the_live_repo_matches_483(capsys) -> None:
    # The real tree, not a fixture: every variable this check reports must be
    # an EXEMPTED one today. If E2E_PERF or E2E_OIDC is ever set in CI, the
    # exemption goes stale and this goes red, which is the point.
    root = Path(__file__).resolve().parents[4]
    code = gate.main(["gate", "--root", str(root)])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "E2E_PERF" in out and "E2E_OIDC" in out, out
