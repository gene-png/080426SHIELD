"""The e2e spec-listing check (#540): a spec on disk CI's run excludes is a finding.

The owner's design for #540's Playwright half: compare the specs on disk with
the specs the CI project runs. Written with the check; the live-repo test at
the bottom pins the listing step to CI's real run step.
"""

from __future__ import annotations

import pathlib
from pathlib import Path

import pytest

# The DOTTED form, deliberately: see test_leave_row_oracle_anchors.py for why a
# bare `from scripts import ...` sorts differently in the container and in CI.
import scripts.check_e2e_spec_listing as gate
import yaml

from tests._paths import find_workflows_dir

pytestmark = pytest.mark.unit


def _listing(*specs: str) -> str:
    lines = ["Listing tests:"]
    lines += [f"  [chromium] › {s}:10:5 › a test" for s in specs]
    lines.append(f"Total: {len(specs)} tests in {len(specs)} files")
    return "\n".join(lines) + "\n"


def _repo(tmp_path: Path, on_disk: list[str], listing: str) -> tuple[Path, Path]:
    for rel in on_disk:
        p = tmp_path / "e2e" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("test('x', () => {});\n", encoding="utf-8")
    lst = tmp_path / "list.txt"
    lst.write_text(listing, encoding="utf-8")
    return tmp_path, lst


def _run(root: Path, lst: Path, capsys) -> tuple[int, str]:
    code = gate.main(["gate", "--root", str(root), "--list-file", str(lst)])
    return code, capsys.readouterr().out


def test_every_spec_listed_is_clean(tmp_path, capsys) -> None:
    root, lst = _repo(
        tmp_path, ["smoke/a.spec.ts", "b.spec.ts"], _listing("smoke/a.spec.ts", "b.spec.ts")
    )
    code, out = _run(root, lst, capsys)
    assert code == 0, out
    assert "all 2 spec file(s)" in out, out


def test_a_spec_on_disk_the_run_excludes_is_a_finding_naming_it(tmp_path, capsys) -> None:
    root, lst = _repo(tmp_path, ["smoke/a.spec.ts", "b.spec.ts"], _listing("b.spec.ts"))
    code, out = _run(root, lst, capsys)
    assert code == 1, out
    assert "e2e/smoke/a.spec.ts: not in `npx playwright test --list`" in out, out


def test_windows_separators_in_the_listing_are_normalised(tmp_path, capsys) -> None:
    # --list prints `smoke\\a.spec.ts` on Windows; the author's own first
    # negative test grepped for a forward-slash path and removed nothing.
    root, lst = _repo(tmp_path, ["smoke/a.spec.ts"], _listing("smoke" + chr(92) + "a.spec.ts"))
    code, out = _run(root, lst, capsys)
    assert code == 0, out


def test_node_modules_specs_are_not_counted(tmp_path, capsys) -> None:
    root, lst = _repo(tmp_path, ["a.spec.ts", "node_modules/pkg/x.spec.ts"], _listing("a.spec.ts"))
    code, out = _run(root, lst, capsys)
    assert code == 0, out


@pytest.mark.parametrize(
    "listing",
    ["", "Listing tests:\n", "Listing tests:\nTotal: 0 tests in 0 files\n"],
    ids=["empty", "no-total", "no-specs"],
)
def test_a_listing_that_is_not_one_is_could_not_look(tmp_path, capsys, listing: str) -> None:
    root, lst = _repo(tmp_path, ["a.spec.ts"], listing)
    code, out = _run(root, lst, capsys)
    assert code == 2, out


def test_a_missing_list_file_is_could_not_look(tmp_path, capsys) -> None:
    root, _ = _repo(tmp_path, ["a.spec.ts"], _listing("a.spec.ts"))
    code, out = _run(root, tmp_path / "absent.txt", capsys)
    assert code == 2, out


def test_no_e2e_dir_is_could_not_look(tmp_path, capsys) -> None:
    lst = tmp_path / "list.txt"
    lst.write_text(_listing("a.spec.ts"), encoding="utf-8")
    code, out = _run(tmp_path, lst, capsys)
    assert code == 2, out
    # The BRANCH, not only the code: without this guard rglob on a missing
    # directory falls through to "no *.spec.ts under", also exit 2.
    assert "does not exist -- wrong root?" in out, out


def test_list_file_is_required_and_unknown_flags_refused(capsys) -> None:
    assert gate.main(["gate", "--root", "."]) == 2
    assert gate.main(["gate", "--lst", "x"]) == 2


def test_the_listing_step_lists_exactly_what_the_e2e_run_step_runs() -> None:
    # The listing is only evidence about CI's run if it uses the same cwd and
    # arguments. Parse ci.yml: the e2e job's main run is `npx playwright test`
    # with no arguments, and the listing step lists with no others either.
    wf = find_workflows_dir(pathlib.Path(__file__).resolve())
    if wf is None:
        pytest.skip("no .github/workflows above this file (the api container mounts apps/api)")
    job = yaml.safe_load((wf / "ci.yml").read_text(encoding="utf-8"))["jobs"]["e2e"]
    runs = [(s.get("working-directory"), str(s.get("run") or "").strip()) for s in job["steps"]]
    assert ("e2e", "npx playwright test") in runs, runs
    listing = [r for r in runs if "playwright test --list" in r[1]]
    assert len(listing) == 1, listing
    wd, script = listing[0]
    assert wd == "e2e", listing
    assert script.splitlines()[0].startswith("npx playwright test --list >"), script


def test_a_truncated_listing_with_specs_but_no_total_is_could_not_look(tmp_path, capsys) -> None:
    # A listing cut off before its `Total:` line may be missing specs, so it
    # cannot certify that every spec on disk is in the run. Without this row the
    # `Total:` check turned nothing red when removed (the other could-not-look
    # rows name no spec, and the no-specs branch caught them first).
    truncated = "Listing tests:\n  [chromium] › a.spec.ts:10:5 › a test\n"
    root, lst = _repo(tmp_path, ["a.spec.ts"], truncated)
    code, out = _run(root, lst, capsys)
    assert code == 2, out
