"""The control-character gate must fail closed, and be able to fail at all.

CLAUDE.md records the counter-example this file exists to avoid: the fail-closed
lesson "demonstrably worked" for `check_issue_references.py` because its
fail-closed path AND the test pinning it were in the first committed version.
`check_no_control_chars.py` shipped without either, and the adversarial review of
the branch that added it found two real defects in it -- a per-file `continue`
that counted unreadable files as scanned, and a dead `CR` check. Both are pinned
below.

Exit codes under test: 0 clean, 1 violation found, 2 could not read the input.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.check_no_control_chars import main

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_no_control_chars.py"


def _run(root: Path) -> int:
    """Call main() directly rather than shelling out.

    Matches `test_issue_reference_guard.py`, keeps the run fast, and avoids the
    S603 subprocess lint. `main` returns 0/1/2 uniformly and never raises, which
    is what makes this possible.
    """
    return main(["check_no_control_chars", str(root)])


@pytest.mark.unit
def test_the_script_exists_where_ci_calls_it(capsys: pytest.CaptureFixture[str]) -> None:
    """CI invokes it by path from the repo root; a rename would be a silent skip."""
    assert (
        _SCRIPT.is_file()
    ), f"{_SCRIPT} is missing -- the CI step would fail loudly, but so should this"


@pytest.mark.unit
def test_clean_tree_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "ok.py").write_text(
        "x = 1\n# a comment with a backslash-b: \\b\n", encoding="utf-8"
    )
    (tmp_path / "ok.md").write_text(
        "# Title\n\nProse about `\\v` and `\\u2028`.\n", encoding="utf-8"
    )
    code = _run(tmp_path)
    out = capsys.readouterr().out
    assert code == 0, out
    assert "clean" in out


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name", "codepoint"),
    [
        ("backspace", 0x08),
        ("vertical tab", 0x0B),
        ("form feed", 0x0C),
        ("file separator", 0x1C),
        ("next line", 0x85),
        ("line separator", 0x2028),
        ("paragraph separator", 0x2029),
        ("byte order mark", 0xFEFF),
        ("lone carriage return", 0x0D),
    ],
)
def test_each_forbidden_character_is_caught(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str, codepoint: int
) -> None:
    """One cell per character, so removing any single one from _FORBIDDEN goes red.

    The lone-CR cell is the one that matters most: it was DEAD before the review,
    because `read_text` opened with newline=None and translated every CR to LF
    before the scan. It passes only because the script now decodes bytes itself.
    """
    (tmp_path / "bad.md").write_text(f"prose with {chr(codepoint)} inside\n", encoding="utf-8")
    code = _run(tmp_path)
    out = capsys.readouterr().out
    assert code == 1, f"{name} was not caught: {out}"
    assert f"U+{codepoint:04X}" in out


@pytest.mark.unit
def test_crlf_line_endings_are_not_a_violation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Whether the working tree has CRLF depends on core.autocrlf.

    Flagging it would make the gate disagree between a Windows checkout and CI,
    which is worse than not having the gate -- a check that fails for a reason
    unrelated to the defect gets disabled.
    """
    (tmp_path / "crlf.py").write_bytes(b"x = 1\r\ny = 2\r\n")
    code = _run(tmp_path)
    out = capsys.readouterr().out
    assert code == 0, out


@pytest.mark.unit
def test_tabs_and_newlines_are_not_violations(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "tabs.md").write_text("a\tb\n\nc\n", encoding="utf-8")
    assert _run(tmp_path) == 0


@pytest.mark.unit
def test_a_file_that_is_not_utf8_fails_closed_with_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The finding this test was written for.

    The first version skipped an undecodable file with a bare `continue` and then
    printed `clean (N files)` with N counting it. A file saved UTF-16 or Latin-1
    by a Windows editor is one of the ways a raw 0x85 gets in, so "I could not
    read it" and "there was nothing to find" must not be the same branch.
    """
    (tmp_path / "latin1.md").write_bytes(b"caf\xe9 \x85 not utf-8\n")
    code = _run(tmp_path)
    out = capsys.readouterr().out
    assert code == 2, out
    assert "could not read" in out
    assert "latin1.md" in out


@pytest.mark.unit
def test_an_empty_tree_fails_closed_with_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Input that supports neither reading is not a pass (D-051)."""
    code = _run(tmp_path)
    out = capsys.readouterr().out
    assert code == 2, out
    assert "no text files" in out


@pytest.mark.unit
def test_a_missing_directory_fails_closed_with_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _run(tmp_path / "does-not-exist")
    out = capsys.readouterr().out
    assert code == 2, out


@pytest.mark.unit
def test_vendored_directories_are_not_scanned(tmp_path: Path) -> None:
    """node_modules must not make the gate unusable.

    Pruned during the walk rather than filtered from the results: a Windows
    symlink in there raises WinError 1920 from is_file().
    """
    vendored = tmp_path / "node_modules" / "pkg"
    vendored.mkdir(parents=True)
    (vendored / "index.js").write_text("var x = '\u2028';\n", encoding="utf-8")
    (tmp_path / "src.py").write_text("x = 1\n", encoding="utf-8")
    assert _run(tmp_path) == 0


@pytest.mark.unit
def test_a_source_directory_named_artifacts_is_still_scanned(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The ambiguous-name trap, pinned.

    `e2e/artifacts` is Playwright output; `apps/web/src/app/api/proxy/artifacts`
    is a real Next.js route. A name-based skip excluded BOTH, so the gate was
    quietly narrower than it claimed over two tracked TypeScript files.
    CLAUDE.md records the identical collision for `coverage/` in this same repo.
    """
    route = tmp_path / "apps" / "web" / "src" / "app" / "api" / "proxy" / "artifacts"
    route.mkdir(parents=True)
    (route / "route.ts").write_text("const x = '\u2028';\n", encoding="utf-8")
    code = _run(tmp_path)
    out = capsys.readouterr().out
    assert code == 1, f"a source dir named artifacts was skipped: {out}"
    assert "route.ts" in out


@pytest.mark.unit
def test_the_real_output_directory_is_still_skipped(tmp_path: Path) -> None:
    """...and the path-anchored skip still does its job for e2e/artifacts."""
    out_dir = tmp_path / "e2e" / "artifacts"
    out_dir.mkdir(parents=True)
    (out_dir / "trace.json").write_text('{"x": "\u2028"}\n', encoding="utf-8")
    (tmp_path / "src.py").write_text("x = 1\n", encoding="utf-8")
    assert _run(tmp_path) == 0


@pytest.mark.unit
def test_the_violation_report_names_file_and_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A gate that says "something is wrong" without saying where gets ignored."""
    (tmp_path / "a.md").write_text("line one\nline two \u2028 here\n", encoding="utf-8")
    code = _run(tmp_path)
    out = capsys.readouterr().out
    assert code == 1
    assert "a.md:2" in out, out
