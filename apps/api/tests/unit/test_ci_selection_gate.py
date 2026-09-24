"""The CI-selection gate (#540): a test that exists but CI never runs is a finding.

Written BEFORE the gate. Two instances in one day prompted it: the #535/#536
leak tests shipped unmarked, so CI's `pytest -m unit tests/unit` would have
selected 0 of their 61 tests, and local runs that named the file directly
passed; and #483, Playwright specs gated on environment variables no workflow
sets. `check_test_integrity.py` catches tests that cannot fail; nothing caught
tests that never run.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

# The DOTTED form, deliberately: see test_leave_row_oracle_anchors.py for why a
# bare `from scripts import ...` sorts differently in the container and in CI.
import scripts.check_ci_selection as gate

pytestmark = pytest.mark.unit


def _project(tmp_path: Path, files: dict[str, str]) -> Path:
    """A throwaway pytest project with the `unit` marker registered."""
    (tmp_path / "pytest.ini").write_text("[pytest]\nmarkers =\n    unit: fast\n", encoding="utf-8")
    for rel, body in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(body), encoding="utf-8")
    return tmp_path


MARKED = """
    import pytest
    pytestmark = pytest.mark.unit
    def test_a(): pass
    def test_b(): pass
"""
UNMARKED = """
    def test_c(): pass
    def test_d(): pass
    def test_e(): pass
"""


def _baseline(tmp_path: Path, entries: dict) -> Path:
    p = tmp_path / "baseline.json"
    p.write_text(json.dumps(entries), encoding="utf-8")
    return p


# --- parsing: the collector's output, in both formats pytest prints ----------


def test_parse_reads_the_per_file_count_format() -> None:
    out = "tests/unit/test_x.py: 3\ntests/unit/test_y.py: 12\n"
    assert gate.parse_collection(out) == {"tests/unit/test_x.py": 3, "tests/unit/test_y.py": 12}


def test_parse_reads_the_node_id_format() -> None:
    out = "tests/unit/test_x.py::test_a\ntests/unit/test_x.py::test_b[1]\ntests/unit/test_y.py::test_c\n"
    assert gate.parse_collection(out) == {"tests/unit/test_x.py": 2, "tests/unit/test_y.py": 1}


def test_parse_of_unrecognised_output_is_empty_not_a_guess() -> None:
    # The author's own first count grepped for `::` against `file: N` output
    # and read 0 for everything. An unparseable collection must never become a
    # count of zero that reads as "nothing unselected".
    assert gate.parse_collection("collected 5 items\n\n5 tests collected in 0.1s\n") == {}


# --- the verdict --------------------------------------------------------------


def test_an_unmarked_file_is_a_finding_naming_the_file_and_count(tmp_path, capsys) -> None:
    root = _project(tmp_path, {"tests/unit/test_m.py": MARKED, "tests/unit/test_u.py": UNMARKED})
    code = gate.main(["gate", "--root", str(root), "--baseline", str(_baseline(tmp_path, {}))])
    out = capsys.readouterr().out
    assert code == 1, out
    assert "tests/unit/test_u.py" in out and "3 of 3" in out, out


def test_all_marked_is_clean_and_says_what_it_counted(tmp_path, capsys) -> None:
    root = _project(tmp_path, {"tests/unit/test_m.py": MARKED})
    code = gate.main(["gate", "--root", str(root), "--baseline", str(_baseline(tmp_path, {}))])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "2 of 2" in out, out


def test_a_baselined_file_with_a_reason_passes_and_is_still_printed(tmp_path, capsys) -> None:
    root = _project(tmp_path, {"tests/unit/test_m.py": MARKED, "tests/unit/test_u.py": UNMARKED})
    base = _baseline(
        tmp_path, {"tests/unit/test_u.py": {"unselected": 3, "reason": "#500: unmarked"}}
    )
    code = gate.main(["gate", "--root", str(root), "--baseline", str(base)])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "tests/unit/test_u.py" in out and "#500: unmarked" in out, out


def test_a_baselined_file_that_GREW_is_a_finding(tmp_path, capsys) -> None:
    root = _project(tmp_path, {"tests/unit/test_u.py": UNMARKED})
    base = _baseline(tmp_path, {"tests/unit/test_u.py": {"unselected": 2, "reason": "#500"}})
    code = gate.main(["gate", "--root", str(root), "--baseline", str(base)])
    assert code == 1, capsys.readouterr().out


def test_a_baseline_entry_that_SHRANK_is_a_finding_so_the_backlog_ratchets(
    tmp_path, capsys
) -> None:
    root = _project(tmp_path, {"tests/unit/test_m.py": MARKED})
    base = _baseline(tmp_path, {"tests/unit/test_m.py": {"unselected": 2, "reason": "#500"}})
    code = gate.main(["gate", "--root", str(root), "--baseline", str(base)])
    out = capsys.readouterr().out
    assert code == 1, out
    assert "shrink" in out.lower(), out


def test_a_baseline_entry_without_a_reason_is_refused(tmp_path, capsys) -> None:
    root = _project(tmp_path, {"tests/unit/test_u.py": UNMARKED})
    base = _baseline(tmp_path, {"tests/unit/test_u.py": {"unselected": 3, "reason": "  "}})
    code = gate.main(["gate", "--root", str(root), "--baseline", str(base)])
    assert code == 2, capsys.readouterr().out


# --- could not look: never clean (D-051) --------------------------------------


def test_the_wrong_directory_is_could_not_look_not_clean(tmp_path, capsys) -> None:
    # #524's shape: a cwd-relative path that resolves to nothing must not read
    # as "nothing unselected".
    code = gate.main(["gate", "--root", str(tmp_path), "--baseline", str(_baseline(tmp_path, {}))])
    assert code == 2, capsys.readouterr().out


def test_an_empty_collection_is_could_not_look(tmp_path, capsys) -> None:
    root = _project(tmp_path, {"tests/unit/__init__.py": ""})
    code = gate.main(["gate", "--root", str(root), "--baseline", str(_baseline(tmp_path, {}))])
    assert code == 2, capsys.readouterr().out


def test_a_missing_baseline_is_could_not_look(tmp_path, capsys) -> None:
    root = _project(tmp_path, {"tests/unit/test_m.py": MARKED})
    code = gate.main(["gate", "--root", str(root), "--baseline", str(tmp_path / "absent.json")])
    assert code == 2, capsys.readouterr().out


def test_an_unknown_argument_is_could_not_look(capsys) -> None:
    assert gate.main(["gate", "--baselin", "x"]) == 2


# --- the selector is CI's, not a copy that can drift from it -------------------


def test_the_gates_selector_is_the_one_ci_runs() -> None:
    ci = (Path(__file__).resolve().parents[4] / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    assert f"run: pytest {' '.join(gate.CI_SELECTOR)}" in ci, (
        f"ci.yml no longer runs `pytest {' '.join(gate.CI_SELECTOR)}`; the gate "
        "would be certifying a selector CI does not use"
    )
