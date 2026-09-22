"""The size gate's constant, its units, and the half `--limit` cannot reach.

`tests/gates/check_claude_md_size/` proves the gate DISCRIMINATES -- it passes a
small file, refuses a large one, and fails closed on input it cannot read. All
of those run against a small `--limit`, because the honest negative control at
the real bar is a 150,001-byte blob in the fixture tree.

So the fixtures cannot see the 150,000 constant, and a constant is exactly the
thing a negative control cannot prove: the gate would behave identically with
the number set to 2,000,000, and every fixture would still pass while the file
went on being truncated. That is this file's job, and it is the reason the gate
carries a flag at all.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
GATE = SCRIPTS / "check_claude_md_size.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_claude_md_size", GATE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    # noqa justified: every argument is built here from a repo-relative path and
    # `sys.executable`. Running it as a real process is the point -- importing
    # would not exercise the argv handling this file is about.
    return subprocess.run(  # noqa: S603
        [sys.executable, str(GATE), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )


@pytest.mark.unit
def test_the_limit_is_the_measured_cliff_not_a_preference() -> None:
    """150,000 is where a reader was OBSERVED to cut the file on 2026-09-22.

    Pinned because the fixtures run against `--limit` and therefore cannot see
    this number. If a future reader is measured truncating LOWER, this
    assertion is the thing that has to be edited deliberately, with the new
    measurement -- which is the point. Raising it is what the gate exists to
    make someone argue for out loud.
    """
    assert _load().LIMIT_BYTES == 150_000


@pytest.mark.unit
def test_the_line_budget_is_reported_and_not_enforced() -> None:
    """CLAUDE.md's own 600-line budget is ~40,000 bytes.

    Enforcing it today would hold the repo permanently red, which teaches
    everyone to route around the gate. The gate prints the overage and returns
    0; this pins that the two numbers are kept apart.
    """
    mod = _load()
    assert mod.SELF_IMPOSED_LINE_BUDGET == 600
    assert mod.SELF_IMPOSED_LINE_BUDGET * 100 < mod.LIMIT_BYTES


@pytest.mark.unit
def test_bytes_and_characters_are_measured_separately(tmp_path: Path) -> None:
    """The unit is BYTES, and the two genuinely differ on this repo's prose.

    CLAUDE.md measured 210,958 bytes against 210,215 characters -- 743 bytes of
    multi-byte UTF-8, mostly em-dashes. A gate written against `len(text)` would
    have reported the file 743 bytes safer than it was.
    """
    f = tmp_path / "x.md"
    f.write_text("—" * 10, encoding="utf-8")  # 10 chars, 30 bytes
    size, chars, _lines = _load().measure(f)
    assert (size, chars) == (30, 10)


@pytest.mark.unit
def test_limit_may_lower_the_bar(tmp_path: Path) -> None:
    f = tmp_path / "CLAUDE.md"
    f.write_text("x" * 5000, encoding="utf-8")
    assert _run("--limit", "1000", str(f)).returncode == 1
    assert _run("--limit", "9000", str(f)).returncode == 0


@pytest.mark.unit
def test_limit_may_not_raise_the_bar(tmp_path: Path) -> None:
    """The flag must not become the hole.

    Without this, anyone hitting a red gate can pass the number that makes
    their file legal, and "DO NOT RAISE THE LIMIT" is advice rather than a
    property. Exit 2, not 0: choosing an impossible bar is a could-not-look,
    not a pass.
    """
    f = tmp_path / "CLAUDE.md"
    f.write_text("x" * 10, encoding="utf-8")
    done = _run("--limit", str(_load().LIMIT_BYTES + 1), str(f))
    assert done.returncode == 2
    assert "may only lower the bar" in done.stdout


@pytest.mark.unit
def test_an_empty_file_passes_rather_than_failing_closed(tmp_path: Path) -> None:
    """Stated in the docstring, pinned here because it is the arguable call.

    This gate's proposition is "small enough to be read whole", and a zero-byte
    file satisfies it. Whether the file has CONTENT is a different proposition,
    and answering an adjacent one is the certificate-over-the-wrong-proposition
    shape.
    """
    f = tmp_path / "CLAUDE.md"
    f.write_bytes(b"")
    assert _run(str(f)).returncode == 0


@pytest.mark.unit
def test_repo_root_finds_the_marker_and_raises_when_there_is_none(tmp_path: Path) -> None:
    """Both directions, because a guard seen only in the state that fires is
    not a guard that has been checked."""
    mod = _load()
    root = tmp_path / "repo"
    (root / ".github").mkdir(parents=True)
    (root / "apps").mkdir()
    deep = root / "apps" / "api" / "scripts"
    deep.mkdir(parents=True)
    assert mod.repo_root(deep / "x.py") == root

    with pytest.raises(RuntimeError, match="cannot locate a repo root"):
        mod.repo_root(Path(tmp_path.anchor) / "nowhere" / "x.py")


@pytest.mark.unit
def test_a_directory_target_is_a_could_not_look(tmp_path: Path) -> None:
    done = _run(str(tmp_path))
    assert done.returncode == 2
    assert "is a directory" in done.stdout


@pytest.mark.unit
def test_the_soft_line_warns_and_does_not_fail(tmp_path: Path) -> None:
    """A gate that fires with no prepared remedy reads as the gate being broken.

    The soft line exists to arrive EARLY, while there is still room to act, and
    to point at the named candidate list in CLAUDE.md rather than just saying
    no. So it must print and must not change the exit code.
    """
    mod = _load()
    f = tmp_path / "CLAUDE.md"
    f.write_text("x" * (mod.SOFT_LIMIT_BYTES + 10), encoding="utf-8")
    done = _run(str(f))
    assert done.returncode == 0
    assert "SOFT LINE PASSED" in done.stdout
    assert "Where the next 15,000 bytes come from" in done.stdout


@pytest.mark.unit
def test_below_the_soft_line_says_nothing_about_it(tmp_path: Path) -> None:
    """The warning must not fire on every run, or it becomes noise nobody reads."""
    f = tmp_path / "CLAUDE.md"
    f.write_text("x" * 100, encoding="utf-8")
    done = _run(str(f))
    assert done.returncode == 0
    assert "SOFT LINE" not in done.stdout


@pytest.mark.unit
def test_the_real_file_carries_the_canary_as_its_last_line() -> None:
    """The repo's own CLAUDE.md, not a fixture.

    The fixtures prove the CHECK discriminates; this proves the FILE satisfies
    it. Both are needed: a perfect check over a file that never adopted the
    marker protects nothing, and that gap is invisible from inside the fixture
    tree, whose files are also named CLAUDE.md.

    THIS IS THE CONVENIENCE COPY, NOT THE ENFORCEMENT. It SKIPS in the api
    container, which mounts only `apps/api`, so a skip here proves nothing --
    and `CLAUDE.md` records that a spec self-skipping on a precondition is
    UNTESTED rather than passing. The enforcing surface is `ci.yml`'s
    "governance file fits in a reader" step, which runs
    `--require-canary CLAUDE.md` on a full checkout and exits 2 if the marker
    is missing or not last.

    RESIDUAL, stated rather than left to be discovered: if someone drops
    `--require-canary` from that step, this test skips in-container and the
    check silently stops happening. That is the same shape as
    `check_test_integrity`'s correctness living in a `working-directory:` line
    nothing verifies. Not closed here.
    """
    mod = _load()
    try:
        real = mod.repo_root() / "CLAUDE.md"
    except RuntimeError:
        # The api container mounts only `apps/api` at /app, so neither `.github`
        # nor `apps` exists above this file and the real CLAUDE.md is genuinely
        # not present. Skipping is honest here; asserting would be a test about
        # a file that is not there.
        pytest.skip("repo root not reachable (api container mounts only apps/api)")
    if not real.is_file():
        pytest.skip(f"no CLAUDE.md at {real}")
    tail = [ln for ln in real.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert tail[-1] == mod.CANARY


@pytest.mark.unit
def test_a_canary_that_is_not_last_is_a_could_not_look(tmp_path: Path) -> None:
    """Strictly worse than no canary: the reader gets a POSITIVE signal that its
    copy is whole while everything below the marker is missing."""
    mod = _load()
    f = tmp_path / "CLAUDE.md"
    f.write_text(f"# x\n\n{mod.CANARY}\n\n## appended later\n\nlost text\n", encoding="utf-8")
    done = _run("--require-canary", str(f))
    assert done.returncode == 2
    assert "canary is NOT the last line" in done.stdout


@pytest.mark.unit
def test_require_canary_is_not_a_no_op(tmp_path: Path) -> None:
    """The flag must be able to REFUSE, or it could be wired in CI and check
    nothing -- this repo's recorded selector-selects-nothing shape."""
    f = tmp_path / "CLAUDE.md"
    f.write_text("# x\n\nno marker\n", encoding="utf-8")
    assert _run("--require-canary", str(f)).returncode == 2
    assert _run(str(f)).returncode == 0  # and it is OFF by default
