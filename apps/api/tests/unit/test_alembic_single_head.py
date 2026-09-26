"""The migration chain has exactly ONE head and no gaps (Gene's addition 3 to
the #620 design, 2026-09-25).

Several open PRs carry migrations (#620 took 0054; #658 takes 0055 and #640
0056, renumbered 2026-09-26 when the landing order changed), and each is cut
from `main`. Whichever lands second must re-point its
`down_revision`; if it does not, the chain forks, `alembic upgrade head` refuses
to choose, and every containerised gate that runs migrations fails -- or, worse,
a fixture that upgrades to one named head silently skips the other branch.

Read from Alembic's own `ScriptDirectory`, never from filenames: the chain's
order is not the number order (0053 sits BELOW 0052 on `main`), so a filename
check would certify the wrong thing.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

API_ROOT = Path(__file__).resolve().parents[2]


def _scripts() -> ScriptDirectory:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return ScriptDirectory.from_config(cfg)


@pytest.mark.unit
def test_the_chain_has_exactly_one_head_and_one_base() -> None:
    s = _scripts()
    assert len(s.get_heads()) == 1, f"forked chain, heads: {sorted(s.get_heads())}"
    assert len(s.get_bases()) == 1, f"more than one base: {sorted(s.get_bases())}"


@pytest.mark.unit
def test_every_revision_is_on_the_single_line_from_head_to_base() -> None:
    s = _scripts()
    everything = {rev.revision for rev in s.walk_revisions()}
    # Asserted first: a directory Alembic could not read would pass the rest.
    assert len(everything) > 50, f"read {len(everything)} revisions: wrong directory?"
    line: list[str] = []
    rev = s.get_revision(s.get_current_head())
    while rev is not None:
        down = rev.down_revision
        assert not isinstance(down, (tuple, list)), f"{rev.revision} is a merge of {down}"
        line.append(rev.revision)
        rev = s.get_revision(down) if down is not None else None
    assert line[-1] in s.get_bases()
    assert sorted(line) == sorted(
        everything
    ), f"off the head-to-base line: {sorted(everything - set(line))}"
