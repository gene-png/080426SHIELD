"""Run one leg of the Python CI split: deselect every test the OTHER legs were dealt.

    python -m pytest -m unit tests/unit -n 4 -p scripts.shard_deselect ...

CI's Python check runs the unit suite in two legs (`SHIELD_SHARD_OF`), each its
own runner, each with `SHIELD_SHARD_INDEX` set to 1 or 2. This plugin is the
ONLY narrowing between the certified selection and what a leg runs.

THE DEAL. The certified selection (`$RUNNER_TEMP/pytest-selection.txt`, the set
`check_ci_selection.py --selected-out` wrote and CI's run is held to) is SORTED,
and leg `k` of `n` is dealt every `n`th id from position `k - 1`: `deal()`. No
set order, no hash seed, no per-worker state, so every xdist worker and every
leg computes the same partition from the same file. Each leg's selection file is
compared byte for byte by the aggregate (`check_python_shards.py`), so the legs
cannot deal from different sets without that being a finding.

WHAT IT DOES. The controller writes the leg's dealt list to
`$RUNNER_TEMP/pytest-dealt.txt`; each collecting process deselects exactly the
items not in it. A dealt id that is not collected is an error, never a smaller
run.

FAIL CLOSED (D-090). Every way of not knowing what to deal is exit 2 and a
message, never a quiet full or empty run: a missing or malformed variable, a
missing or empty selection, an index outside 1..n, and a leg dealt nothing. The
plugin is inert only when it is not loaded.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

ENV_INDEX = "SHIELD_SHARD_INDEX"
ENV_OF = "SHIELD_SHARD_OF"
ENV_TEMP = "RUNNER_TEMP"
SELECTION_NAME = "pytest-selection.txt"
DEALT_NAME = "pytest-dealt.txt"


class CouldNotDeal(Exception):
    """The deal cannot be made. Maps to exit 2, never to a smaller run."""


def deal(ids: list[str], of: int, index: int) -> list[str]:
    """Leg `index` (1-based) of `of`: every `of`th id of the sorted ids."""
    if of < 1 or not 1 <= index <= of:
        raise CouldNotDeal(f"shard {index} of {of} is not a leg")
    if len(set(ids)) != len(ids):
        raise CouldNotDeal("the selection lists a test twice, so no deal is a partition")
    return sorted(ids)[index - 1 :: of]


def _whole_number(name: str) -> int:
    raw = os.environ.get(name, "")
    if not raw.isascii() or not raw.isdigit():
        raise CouldNotDeal(f"{name} is {raw!r}, not a whole number")
    return int(raw)


def _temp_dir() -> Path:
    raw = os.environ.get(ENV_TEMP, "")
    if not raw:
        raise CouldNotDeal(f"{ENV_TEMP} is not set, so the certified selection cannot be found")
    return Path(raw)


def dealt_ids() -> list[str]:
    """This leg's dealt ids, from the environment and the certified selection."""
    of, index = _whole_number(ENV_OF), _whole_number(ENV_INDEX)
    path = _temp_dir() / SELECTION_NAME
    try:
        ids = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except OSError as exc:
        raise CouldNotDeal(f"cannot read the certified selection {path}: {exc}") from exc
    if not ids:
        raise CouldNotDeal(f"the certified selection {path} is empty")
    mine = deal(ids, of, index)
    if not mine:
        raise CouldNotDeal(f"shard {index} of {of} was dealt none of the {len(ids)} selected tests")
    return mine


def _is_worker(config: pytest.Config) -> bool:
    return hasattr(config, "workerinput")


def pytest_sessionstart(session: pytest.Session) -> None:
    if _is_worker(session.config):
        return
    try:
        mine = dealt_ids()
    except CouldNotDeal as exc:
        pytest.exit(f"shard-deselect: could not deal -- {exc}", returncode=2)
    (_temp_dir() / DEALT_NAME).write_text("".join(f"{i}\n" for i in mine), encoding="utf-8")
    print(
        f"shard-deselect: shard {os.environ[ENV_INDEX]} of {os.environ[ENV_OF]} dealt {len(mine)} tests"
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    try:
        mine = set(dealt_ids())
    except CouldNotDeal as exc:
        raise pytest.UsageError(f"shard-deselect: could not deal -- {exc}") from exc
    kept = [item for item in items if item.nodeid in mine]
    missing = mine - {item.nodeid for item in kept}
    if missing:
        raise pytest.UsageError(
            f"shard-deselect: {len(missing)} dealt test(s) were not collected, first: {min(missing)}"
        )
    dropped = [item for item in items if item.nodeid not in mine]
    if dropped:
        config.hook.pytest_deselected(items=dropped)
    items[:] = kept
