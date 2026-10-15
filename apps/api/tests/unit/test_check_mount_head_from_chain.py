"""The mount check names the chain's HEAD, not the highest-numbered file (for #1058).

`check_mount_matches_database.py` printed `sorted(in_tree)[-1]` as "newest in
tree". This repo's chain order is not its number order: 0072 (TD-2 part A) is
numbered out of order and chains AFTER 0073, so the highest number, 0073, is
not the head. A reader told "newest in tree: 0073" while `alembic heads` says
0072 is sent after the wrong file.

The head is the revision that no other revision names as its `down_revision`.
More than one such revision (a forked chain) or none (a cycle) is a tree whose
head cannot be named, and the gate says it could not look (exit 2) rather than
printing a guess. Fixture chains are written here from the rule, and the
real-tree case is checked against alembic's own `ScriptDirectory`, never
against the code under test.
"""

from __future__ import annotations

import pathlib
import re
import sys

import pytest

_API = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_API / "scripts"))

pytestmark = pytest.mark.unit

#: The chain on `main` once 0072 lands, in both spellings the repo uses.
_OUT_OF_ORDER = {
    "0068_a.py": 'revision: str = "0068"\ndown_revision: str | Sequence[str] | None = None\n',
    "0070_b.py": 'revision = "0070"\ndown_revision = "0068"\n',
    "0073_c.py": 'revision: str = "0073"\ndown_revision: str | Sequence[str] | None = "0070"\n',
    "0072_d.py": 'revision: str = "0072"\ndown_revision: str | Sequence[str] | None = "0073"\n',
}


def _tree(tmp_path: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    versions = tmp_path / "alembic" / "versions"
    versions.mkdir(parents=True)
    for name, body in files.items():
        (versions / name).write_text(body, encoding="utf-8")
    return versions


def _run_stamped_elsewhere(monkeypatch, tmp_path, files: dict[str, str]) -> int:
    """`main` over `files`, with the database stamped at a revision the tree
    lacks: the branch that names the tree's head."""
    import check_mount_matches_database as mod

    _tree(tmp_path, files)
    monkeypatch.setattr(mod, "database_revision", lambda url: "0099")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    monkeypatch.setattr(mod, "__file__", str(tmp_path / "scripts" / "x.py"))
    return mod.main()


def _labelled(err: str, label: str) -> list[str]:
    return re.findall(rf"^\s*{label}\s*:\s*(\S+)\s*$", err, re.M)


def test_the_head_is_the_end_of_the_chain_not_the_highest_number(
    monkeypatch, tmp_path, capsys
) -> None:
    from check_mount_matches_database import EXIT_MISMATCH

    assert _run_stamped_elsewhere(monkeypatch, tmp_path, _OUT_OF_ORDER) == EXIT_MISMATCH
    err = capsys.readouterr().err
    assert _labelled(err, "head of chain in tree") == ["0072"], err
    # The old label, and the highest number under any label, are gone.
    assert "newest in tree" not in err
    assert _labelled(err, "head of chain in tree") != ["0073"]


def test_an_in_order_chain_names_its_last_revision(monkeypatch, tmp_path, capsys) -> None:
    """The control: where number order and chain order agree, the same head."""
    from check_mount_matches_database import EXIT_MISMATCH

    files = {k: v for k, v in _OUT_OF_ORDER.items() if not k.startswith("0072")}
    assert _run_stamped_elsewhere(monkeypatch, tmp_path, files) == EXIT_MISMATCH
    assert _labelled(capsys.readouterr().err, "head of chain in tree") == ["0073"]


def test_a_forked_chain_cannot_name_a_head_and_says_so(monkeypatch, tmp_path, capsys) -> None:
    from check_mount_matches_database import EXIT_COULD_NOT_LOOK

    forked = {
        **_OUT_OF_ORDER,
        "0074_e.py": 'revision = "0074"\ndown_revision = "0073"\n',
    }
    assert _run_stamped_elsewhere(monkeypatch, tmp_path, forked) == EXIT_COULD_NOT_LOOK
    err = capsys.readouterr().err
    assert "could not look" in err
    assert "2 heads" in err and "0072" in err and "0074" in err, err
    # The fact the check DID establish is still said.
    assert "0099" in err


def test_a_cycle_has_no_head_and_says_so(monkeypatch, tmp_path, capsys) -> None:
    from check_mount_matches_database import EXIT_COULD_NOT_LOOK

    cycle = {
        "0001_a.py": 'revision = "0001"\ndown_revision = "0002"\n',
        "0002_b.py": 'revision = "0002"\ndown_revision = "0001"\n',
    }
    assert _run_stamped_elsewhere(monkeypatch, tmp_path, cycle) == EXIT_COULD_NOT_LOOK
    err = capsys.readouterr().err
    assert "could not look" in err
    assert "no head" in err, err


def test_the_real_trees_head_is_alembics() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from check_mount_matches_database import chain_heads

    cfg = Config(str(_API / "alembic.ini"))
    cfg.set_main_option("script_location", str(_API / "alembic"))
    expected = ScriptDirectory.from_config(cfg).get_heads()
    assert len(expected) == 1, expected  # precondition: main has one head
    assert chain_heads(_API / "alembic" / "versions") == expected
