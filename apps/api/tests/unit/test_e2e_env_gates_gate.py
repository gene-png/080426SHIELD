"""The e2e env-gate check (#540, Playwright half): a spec gated on a variable
no workflow sets never runs in CI.

#483 was the instance: `E2E_PERF` and `E2E_OIDC` gated `test.skip(...)` in two
specs, one of them a smoke spec, and no workflow step set either, so both
specs self-skipped on every CI run until #560 (`06fa7ce`) moved them to
`e2e/manual/`. Written BEFORE the check.
"""

from __future__ import annotations

import json
import pathlib
import textwrap
from pathlib import Path

import pytest

# The DOTTED form, deliberately: see test_leave_row_oracle_anchors.py for why a
# bare `from scripts import ...` sorts differently in the container and in CI.
import scripts.check_e2e_env_gates as gate

from tests._paths import find_workflows_dir

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
    # The gate requires exactly one Playwright config (review of 18d24d5).
    (tmp_path / "e2e").mkdir(exist_ok=True)
    (tmp_path / "e2e" / "playwright.config.ts").write_text(
        "export default { testDir: '.' };" + chr(10), encoding="utf-8"
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
        tmp_path,
        {"perf.spec.ts": GATED},
        UNSET_WORKFLOW,
        {"E2E_PERF": {"specs": ["e2e/perf.spec.ts"], "reason": "#483"}},
    )
    code, out = _run(root, capsys)
    assert code == 0, out
    assert "E2E_PERF" in out and "#483" in out, out


def test_an_exemption_for_a_variable_now_set_is_stale(tmp_path, capsys) -> None:
    root = _repo(
        tmp_path,
        {"perf.spec.ts": GATED},
        SET_WORKFLOW,
        {"E2E_PERF": {"specs": ["e2e/perf.spec.ts"], "reason": "#483"}},
    )
    code, out = _run(root, capsys)
    assert code == 1, out
    assert "stale" in out.lower(), out


def test_an_exemption_no_spec_uses_is_stale(tmp_path, capsys) -> None:
    root = _repo(
        tmp_path,
        {"perf.spec.ts": GATED},
        SET_WORKFLOW,
        {"E2E_GONE": {"specs": ["e2e/gone.spec.ts"], "reason": "old"}},
    )
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
    root = _repo(
        tmp_path,
        {"perf.spec.ts": GATED},
        UNSET_WORKFLOW,
        {"E2E_PERF": {"specs": ["e2e/perf.spec.ts"], "reason": " "}},
    )
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


def test_the_live_repo_is_clean_with_only_the_configuration_exemption(capsys) -> None:
    # The real tree, not a fixture. #483's E2E_PERF and E2E_OIDC exemptions are
    # GONE: #560 renamed both specs to `e2e/manual/*.manual.ts` and removed
    # their env reads, so no scanned spec reads either, and this PR removed
    # the exemptions. What remains exempted is E2E_API_URL, configuration with
    # a default. A new ungated variable, or a stale exemption, turns this red.
    # Skipped only with no `.github/workflows` above this file (the api
    # container).
    wf = find_workflows_dir(pathlib.Path(__file__).resolve())
    if wf is None:
        pytest.skip("no .github/workflows above this file (the api container mounts apps/api)")
    code = gate.main(["gate", "--root", str(wf.parent.parent)])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "exempted: E2E_API_URL" in out, out
    assert "E2E_PERF" not in out and "E2E_OIDC" not in out, out


# --- review of e8424dd: what counts as SET, and what counts as a gate -----------

COMMENT_ONLY = """
    jobs:
      e2e:
        steps:
          # E2E_PERF=1 opts the perf spec in
          - run: npx playwright test
"""
DISABLED = """
    jobs:
      e2e:
        steps:
          - env:
              E2E_PERF: "0"
            run: npx playwright test
"""
RUN_EXPORT = """
    jobs:
      e2e:
        steps:
          - run: |
              export E2E_PERF=1   # opt the perf spec in
              npx playwright test
"""
JOB_ENV = """
    jobs:
      e2e:
        env:
          E2E_PERF: "1"
        steps:
          - run: npx playwright test
"""


def test_a_comment_mentioning_the_variable_is_not_setting_it(tmp_path, capsys) -> None:
    # Review of e8424dd: raw-text matching counted ci.yml's own comment
    # "# SHIELD_DEMO_SMOKE=1 opts the demo-journey spec in" as a setting.
    code, out = _run(_repo(tmp_path, {"perf.spec.ts": GATED}, COMMENT_ONLY, {}), capsys)
    assert code == 1, out
    assert "E2E_PERF: read by" in out, out


def test_a_disabling_value_is_not_setting_it(tmp_path, capsys) -> None:
    code, out = _run(_repo(tmp_path, {"perf.spec.ts": GATED}, DISABLED, {}), capsys)
    assert code == 1, out


@pytest.mark.parametrize("workflow", [RUN_EXPORT, JOB_ENV], ids=["run-export", "job-env"])
def test_a_run_script_export_or_job_env_counts_as_set(tmp_path, capsys, workflow: str) -> None:
    code, out = _run(_repo(tmp_path, {"perf.spec.ts": GATED}, workflow, {}), capsys)
    assert code == 0, out


@pytest.mark.parametrize(
    "spec",
    [
        'test("x", () => { test.skip(!process.env["E2E_PERF"], "no"); });',
        'const { E2E_PERF } = process.env; test("x", () => { test.skip(!E2E_PERF, "no"); });',
        'test.describe.skip("x", () => { if (process.env.E2E_PERF) {} });',
        'test("x", ({}, testInfo) => { testInfo.fixme(!process.env.E2E_PERF, "no"); });',
        'test("x", () => { test.skip (!process.env.E2E_PERF, "no"); });',
    ],
    ids=["index-read", "destructure", "describe-skip", "testinfo-fixme", "spaced-skip"],
)
def test_other_spellings_of_a_gate_are_seen(tmp_path, capsys, spec: str) -> None:
    code, out = _run(_repo(tmp_path, {"perf.spec.ts": spec}, UNSET_WORKFLOW, {}), capsys)
    assert code == 1, out
    assert "E2E_PERF" in out, out


# --- review of 3bc0975: exemptions are spec-scoped --------------------------------------


def test_an_exempted_variable_read_by_an_unlisted_spec_is_a_finding(tmp_path, capsys) -> None:
    # E2E_API_URL's exemption was written about one spec's configuration
    # default. Keyed on the name alone, a NEW spec gating on it for real passed.
    root = _repo(
        tmp_path,
        {"perf.spec.ts": GATED, "new.spec.ts": GATED},
        UNSET_WORKFLOW,
        {"E2E_PERF": {"specs": ["e2e/perf.spec.ts"], "reason": "configuration here"}},
    )
    code = gate.main(["gate", "--root", str(root)])
    out = capsys.readouterr().out
    assert code == 1, out
    assert "E2E_PERF: read by e2e/new.spec.ts" in out and "covers only e2e/perf.spec.ts" in out, out


def test_a_listed_spec_that_no_longer_reads_the_variable_is_stale(tmp_path, capsys) -> None:
    root = _repo(
        tmp_path,
        {"perf.spec.ts": GATED},
        UNSET_WORKFLOW,
        {"E2E_PERF": {"specs": ["e2e/perf.spec.ts", "e2e/old.spec.ts"], "reason": "#483"}},
    )
    code = gate.main(["gate", "--root", str(root)])
    out = capsys.readouterr().out
    assert code == 1, out
    assert "exemption is STALE for e2e/old.spec.ts" in out, out


@pytest.mark.parametrize(
    "entry",
    [
        {"reason": "#483"},
        # #580: a STRING is not a list of specs -- iterated, it would be one
        # spec per character -- and an EMPTY list scopes the exemption to
        # nothing. Each must be could-not-look, not a finding or a pass.
        {"reason": "#483", "specs": "e2e/perf.spec.ts"},
        {"reason": "#483", "specs": []},
        {"reason": "#483", "specs": [7]},
    ],
    ids=["missing", "a-string", "empty-list", "not-strings"],
)
def test_an_exemption_with_no_specs_list_is_could_not_look(tmp_path, capsys, entry) -> None:
    root = _repo(tmp_path, {"perf.spec.ts": GATED}, UNSET_WORKFLOW, {"E2E_PERF": entry})
    code = gate.main(["gate", "--root", str(root)])
    out = capsys.readouterr().out
    assert code == 2, out
    assert "E2E_PERF needs a non-empty `specs` list" in out, out


# --- #579: the suite is Playwright's default testMatch, not only `*.spec.ts` -------------


@pytest.mark.parametrize("name", ["perf.spec.tsx", "perf.test.ts", "perf.spec.mjs"])
def test_a_gate_in_any_default_pattern_spec_is_seen(tmp_path, capsys, name: str) -> None:
    root = _repo(tmp_path, {name: GATED}, UNSET_WORKFLOW, {})
    code, out = _run(root, capsys)
    assert code == 1, out
    assert "E2E_PERF" in out and name in out, out


@pytest.mark.parametrize(
    "config",
    [
        "export default { testMatch: '**/*.e2e.ts' };",
        "const testMatch = '**/*.e2e.ts';"
        + chr(10)
        + "export default defineConfig({ testMatch });",
        'export default { "testMatch": "**/*.e2e.ts" };',
    ],
    ids=["key", "shorthand", "quoted-key"],
)
def test_a_config_that_sets_test_match_is_could_not_look(tmp_path, capsys, config: str) -> None:
    root = _repo(tmp_path, {"perf.spec.ts": GATED}, UNSET_WORKFLOW, {})
    (root / "e2e" / "playwright.config.ts").write_text(config + chr(10), encoding="utf-8")
    code, out = _run(root, capsys)
    assert code == 2, out
    assert "sets `testMatch`" in out, out


# --- review of 18d24d5: the config must be found before "no testMatch" --------------------


def test_no_playwright_config_is_could_not_look(tmp_path, capsys) -> None:
    root = _repo(tmp_path, {"perf.spec.ts": GATED}, SET_WORKFLOW, {})
    (root / "e2e" / "playwright.config.ts").unlink()
    code, out = _run(root, capsys)
    assert code == 2, out
    assert "expected exactly one Playwright config" in out and "found 0" in out, out


def test_two_playwright_configs_is_could_not_look(tmp_path, capsys) -> None:
    root = _repo(tmp_path, {"perf.spec.ts": GATED}, SET_WORKFLOW, {})
    (root / "e2e" / "playwright.config.js").write_text(
        "module.exports = {};" + chr(10), encoding="utf-8"
    )
    code, out = _run(root, capsys)
    assert code == 2, out
    assert "found 2" in out, out


def test_an_mts_config_that_sets_test_match_is_could_not_look(tmp_path, capsys) -> None:
    root = _repo(tmp_path, {"perf.spec.ts": GATED}, SET_WORKFLOW, {})
    (root / "e2e" / "playwright.config.ts").unlink()
    (root / "e2e" / "playwright.config.mts").write_text(
        "export default { testMatch: '**/*.e2e.ts' };" + chr(10), encoding="utf-8"
    )
    code, out = _run(root, capsys)
    assert code == 2, out
    assert "playwright.config.mts sets `testMatch`" in out, out
