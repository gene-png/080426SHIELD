"""Coverage rows a test may SCORE directly (#554, D-094).

Since D-094, a parent technique with sub-techniques has its status computed from
them: the PATCH refuses it and a run-ai suggestion for it is refused whole. Tests
that scored "the first coverage row" were scoring T1001, a computed parent, and
some of them ignored the PATCH response, so they could pass while nothing was
written.

A STANDALONE technique has no parent and no sub-techniques, so scoring it can
never be refused as a parent's and never completes a family that recomputes a
parent. Derived from the catalog's own parent links, NOT from `app.attack.parents`,
so the setup does not agree with the code under test by construction.
"""

from __future__ import annotations

from app.attack.catalog import TECHNIQUES


def _standalone_codes() -> set[str]:
    has_children = {t.parent_id for t in TECHNIQUES if t.parent_id is not None}
    return {t.id for t in TECHNIQUES if t.parent_id is None and t.id not in has_children}


def standalone_rows(coverage: list[dict], n: int = 1) -> list[dict]:
    """The first `n` rows of `coverage` (API-shaped dicts) that are standalone."""
    codes = _standalone_codes()
    rows = [r for r in coverage if r["technique_code"] in codes][:n]
    assert len(rows) == n, f"wanted {n} standalone techniques, the assessment has {len(rows)}"
    return rows


def first_standalone(coverage: list[dict]) -> dict:
    return standalone_rows(coverage, 1)[0]
