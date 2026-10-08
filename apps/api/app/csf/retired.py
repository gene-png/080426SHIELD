"""Rows stored against a subcategory the CSF catalog no longer has (#852).

#852 corrected the CSF catalog to NIST CSWP 29: CSF 2.0 has no `ID.AM-09`.
Migration 0064 KEEPS every row an assessment stored under it, in `csf_answers`,
`csf_dimension_scores` and `csf_gap_actions`, rather than delete them, as the ZT
catalog corrections did (`app.zt.retired`). The scoring and gap engines iterate
the catalog, so those rows are not scored; every reader of STORED rows filters
to `catalog_rows` (or `all_codes()`) itself.

This module is the ONE derivation of how many of them hold an answer and of the
sentences that disclose it. The workspace and the self-assessment
(`routes/csf.py`), the deliverable (`csf/exporters.py`), the client dashboard
(`routes/clients.py`), the Working Profile panel and the playbook files all
call it, so no two of them can disagree. The sentences are the approved copy
(#736 comment 6054419744); change them only with a new approval.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.csf.catalog import all_codes

_SOURCE = "NIST CSF 2.0"


def catalog_rows[T](rows: Iterable[T]) -> list[T]:
    """The rows whose `subcategory_code` the catalog has. Every reader of
    stored rows that scores, lists or sends them goes through this."""
    valid = all_codes()
    return [r for r in rows if r.subcategory_code in valid]  # type: ignore[attr-defined]


def _blank(text: str | None) -> bool:
    return not (text or "").strip()


def has_recorded_answer(answer: Any) -> bool:
    """A tier, notes with text, or evidence: anything someone recorded on a
    `CsfAnswer`. An empty row is not an answer."""
    return (
        answer.maturity_tier is not None
        or not _blank(answer.notes)
        or answer.evidence_artifact_id is not None
    )


def has_recorded_score(row: Any) -> bool:
    """Anything written on a `CsfDimensionScore` beyond what seeding writes.

    A seeded row is all zeros with `answer_source` NULL, so "has a value" cannot
    serve: 0 is a legitimate score. A row the AI or a consultant wrote carries
    `answer_source`; a value differing from the seed default counts as well."""
    return (
        row.answer_source is not None
        or any(
            getattr(row, f) != 0
            for f in ("governance", "policy", "implementation", "monitoring", "improvement")
        )
        or not _blank(row.rationale)
        or not _blank(row.what_we_found)
        or row.evidence_artifact_id is not None
        or bool(row.has_evidence)
        or row.target_level is not None
        or not row.in_scope
    )


def has_recorded_action(action: Any) -> bool:
    """Any field set on a `CsfGapAction`."""
    return any(
        not _blank(getattr(action, f))
        for f in (
            "characterization",
            "priority_override",
            "owner",
            "deadline",
            "resources",
            "success_criteria",
            "poam_ref",
        )
    )


def _retired(rows: Iterable[Any], recorded) -> list[Any]:
    valid = all_codes()
    return [r for r in rows if r.subcategory_code not in valid and recorded(r)]


def _codes(rows: Iterable[Any]) -> list[str]:
    return sorted({r.subcategory_code for r in rows})


def _named(codes: list[str]) -> str:
    """ "ID.AM-09, a subcategory NIST CSF 2.0 does not have", or the plural."""
    if len(codes) == 1:
        return f"{codes[0]}, a subcategory {_SOURCE} does not have"
    return f"{', '.join(codes)}, subcategories {_SOURCE} does not have"


def retired_answers(answers: Iterable[Any]) -> list[Any]:
    """The stored answers on a code the catalog does not have that hold one."""
    return _retired(answers, has_recorded_answer)


def answers_sentence(answers: Iterable[Any]) -> str | None:
    """S1: the approved disclosure for kept answers, or None when none."""
    kept = retired_answers(answers)
    if not kept:
        return None
    n = len(kept)
    if n == 1:
        return f"1 recorded answer belongs to {_named(_codes(kept))}, so it is not scored."
    return f"{n} recorded answers belong to {_named(_codes(kept))}, so they are not scored."


def retired_scores(rows: Iterable[Any]) -> list[Any]:
    """The stored Working Profile rows on a code the catalog does not have that
    someone wrote."""
    return _retired(rows, has_recorded_score)


def working_profile_sentence(rows: Iterable[Any], actions: Iterable[Any]) -> str | None:
    """S2: the approved disclosure for kept Working Profile rows, with the
    action-plan tail when action plans were recorded on the same codes."""
    kept = retired_scores(rows)
    kept_actions = _retired(actions, has_recorded_action)
    if not kept and not kept_actions:
        return None
    if not kept:
        # Not the approved copy's shape: an action plan on a kept code with no
        # recorded row under it. No screen writes one (the action editor lists
        # only gaps, and a gap needs a target), so this is unreachable through
        # the product; it is stated rather than dropped.
        m = len(kept_actions)
        plans = "1 action plan" if m == 1 else f"{m} action plans"
        verb = "is" if m == 1 else "are"
        return f"{plans} recorded for {_named(_codes(kept_actions))} {verb} kept and not listed."
    n = len(kept)
    named = _named(_codes(kept))
    if n == 1:
        out = (
            f"1 recorded Working Profile row belongs to {named}, "
            "so it is not scored or rolled up."
        )
    else:
        out = (
            f"{n} recorded Working Profile rows belong to {named}, "
            "so they are not scored or rolled up."
        )
    m = len(kept_actions)
    if m:
        them = "it" if len(_codes(kept)) == 1 else "them"
        if m == 1:
            out += f" 1 action plan recorded for {them} is kept and not listed."
        else:
            out += f" {m} action plans recorded for {them} are kept and not listed."
    return out
