"""#102 / plan 5.1: the whole state space of "is this technique's support confirmed?"

Written BEFORE the persistence wiring, deliberately. CLAUDE.md records why: a
rule that keeps changing shape is a design problem, not a bug list, and "a matrix
written after the fix only pins the fix." The ZT severity rule was wrong in three
consecutive adversarial rounds because each round fixed the case in front of it.
This enumerates the space first.

## The space

A coverage row carries three things that decide whether its status may score:

* **status** — `None` (unscored), `not_applicable`, `gap`, `partial`, `covered`.
* **`unconfirmed_citations`** — the migration-0044 tri-state: `None` (citations
  were never resolved; the row predates the resolver), `[]` (resolved, nothing
  needed inferring), or a list of `{tool, reason, field, cleared_at}` entries.
* **the tool lists** — `detection_tools` / `prevention_tools` / `response_tools`.

Those collapse to two derived booleans, and the matrix below is the product of
them with status:

* `resolved` — the column is not NULL.
* `backed`   — at least one cited tool is CONFIRMED, meaning it appears in a tool
  list and is NOT named by an uncleared entry.
* `offered`  — something was cited for this row and is not confirmed: an entry
  awaiting a human (`tool` set) or one that resolved to nothing (`tool: null`).

The third boolean is the one the first draft of this file did not have, and its
absence was a real defect rather than a missing test case. Without it, "the model
cited Qradar and we dropped it" and "a consultant typed `covered` by hand"
are the same stored state, so the rule that caught the first also withheld the
second — `test_heatmap_reflects_coverage_after_patches` reported 0 covered and 0%
over ten hand-curated techniques, with nothing in the product able to clear it.
See `app/attack/pending.py` for the three cases written out.

## Three fixture facts the booleans hide, pinned by their own cases below

1. **NULL is not `[]`.** NULL scores as PENDING (migration 0044's docstring; the
   fail-open reading D-054 rejected one layer up). `[]` scores as confirmed.
2. **Cleared is not uncleared.** An entry with `cleared_at` set is a human
   vouching for the inference, which is confirmation per 5.1's second clause.
3. **`backed` can be false three ways** — no tools at all, every tool flagged and
   uncleared, or the tools removed out from under a flag. Whether that withholds
   the claim depends on `offered`, not on which of the three it was.
4. **A rejection is stored, and a rejection is not a tool.** Its entry carries
   `tool: null` and the string the model actually sent, so it can never cancel
   out a tool in the row's lists — only witness that evidence was offered and
   lost.
"""

from __future__ import annotations

import pytest

from app.attack.pending import is_pending_review

_CLEARED = "2026-08-21T00:00:00+00:00"


def _flag(tool: str, *, cleared: bool = False) -> dict:
    """An INFERRED citation: applied under `tool`, awaiting a human."""
    return {
        "tool": tool,
        "cited": tool.split()[0],
        "reason": "vendor",
        "field": "detection_tools",
        "cleared_at": _CLEARED if cleared else None,
    }


def _rejected(cited: str, *, cleared: bool = False) -> dict:
    """A REJECTED citation: resolved to nothing, so it applies no tool."""
    return {
        "tool": None,
        "cited": cited,
        "reason": "rejected_unknown",
        "field": "detection_tools",
        "cleared_at": _CLEARED if cleared else None,
    }


# (label, status, unconfirmed_citations, tools, expected_pending)
#
# Read the four blocks as: what each status is WORTH when its support is
# missing. Only `covered` and `partial` make a positive claim, so only they can
# have one withheld.
_MATRIX: list[tuple[str, str | None, list | None, list[str], bool]] = [
    # --- unscored: no status, so nothing to withhold -----------------------
    ("unscored / never resolved", None, None, [], False),
    ("unscored / resolved clean", None, [], [], False),
    ("unscored / flagged tool", None, [_flag("Splunk")], ["Splunk"], False),
    # --- not_applicable: outside `addressable` already ---------------------
    ("na / never resolved", "not_applicable", None, [], False),
    ("na / resolved clean", "not_applicable", [], [], False),
    ("na / flagged tool", "not_applicable", [_flag("Splunk")], ["Splunk"], False),
    # --- gap: an ABSENCE claim. It needs no support, so none can be
    #     withheld -- and withholding it would DELETE a finding while raising
    #     coverage_pct, which is the optimistic direction 5.1 exists to stop.
    #     See test_withholding_a_gap_would_raise_the_score.
    ("gap / never resolved", "gap", None, [], False),
    ("gap / resolved clean", "gap", [], [], False),
    ("gap / flagged tool", "gap", [_flag("Splunk")], ["Splunk"], False),
    ("gap / no tools but flagged", "gap", [_flag("Splunk")], [], False),
    ("gap / every citation rejected", "gap", [_rejected("Qradar")], [], False),
    # --- covered: a positive claim, so it must be backed -------------------
    ("covered / never resolved", "covered", None, ["Splunk"], True),
    ("covered / never resolved, no tools", "covered", None, [], True),
    ("covered / resolved, confirmed tool", "covered", [], ["Splunk"], False),
    # Case 3: nothing was cited, so there is no unconfirmed evidence to withhold
    # the claim. This is the hand-curated row -- a consultant setting `covered`
    # in the matrix -- and the consultant is the author of the claim, not a
    # reviewer of the model's. Treating it as pending withheld the entire manual
    # workflow with no way to clear it.
    ("covered / resolved, nothing ever cited", "covered", [], [], False),
    # Case 2: something WAS cited and it is gone. Same empty tool list as the row
    # above, opposite verdict, and the stored rejection is the only thing that
    # tells them apart.
    ("covered / every citation rejected", "covered", [_rejected("Qradar")], [], True),
    (
        "covered / rejection a human accepted",
        "covered",
        [_rejected("Qradar", cleared=True)],
        [],
        False,
    ),
    (
        "covered / rejection beside a confirmed tool",
        "covered",
        [_rejected("Qradar")],
        ["Splunk"],
        False,
    ),
    (
        "covered / rejection cannot cancel a flagged tool",
        "covered",
        [_flag("Splunk"), _rejected("Qradar")],
        ["Splunk"],
        True,
    ),
    ("covered / every tool flagged", "covered", [_flag("Splunk")], ["Splunk"], True),
    ("covered / every flag cleared", "covered", [_flag("Splunk", cleared=True)], ["Splunk"], False),
    (
        "covered / mixed, one confirmed",
        "covered",
        [_flag("Splunk")],
        ["Splunk", "CrowdStrike Falcon"],
        False,
    ),
    (
        "covered / mixed, cleared + uncleared",
        "covered",
        [_flag("Splunk"), _flag("Qradar", cleared=True)],
        ["Splunk", "Qradar"],
        False,
    ),
    ("covered / flag whose tool was removed", "covered", [_flag("Splunk")], [], True),
    # --- partial: the same claim at half weight ----------------------------
    ("partial / never resolved", "partial", None, ["Splunk"], True),
    ("partial / resolved, confirmed tool", "partial", [], ["Splunk"], False),
    ("partial / resolved, nothing ever cited", "partial", [], [], False),
    ("partial / every citation rejected", "partial", [_rejected("Qradar")], [], True),
    ("partial / every tool flagged", "partial", [_flag("Splunk")], ["Splunk"], True),
    ("partial / every flag cleared", "partial", [_flag("Splunk", cleared=True)], ["Splunk"], False),
]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("label", "status", "citations", "tools", "expected"),
    _MATRIX,
    ids=[row[0] for row in _MATRIX],
)
def test_pending_matrix(
    label: str,
    status: str | None,
    citations: list | None,
    tools: list[str],
    expected: bool,
) -> None:
    assert is_pending_review(status, citations, tools) is expected, label


@pytest.mark.unit
def test_the_matrix_covers_every_status() -> None:
    """A row nobody listed is the failure mode this file exists to prevent."""
    listed = {row[1] for row in _MATRIX}
    assert listed == {None, "not_applicable", "gap", "partial", "covered"}


@pytest.mark.unit
def test_the_matrix_covers_all_three_column_states() -> None:
    """NULL / [] / non-empty are three DIFFERENT answers, not two."""
    kinds = set()
    for _, _, citations, _, _ in _MATRIX:
        if citations is None:
            kinds.add("null")
        elif not citations:
            kinds.add("empty")
        else:
            kinds.add("populated")
    assert kinds == {"null", "empty", "populated"}


@pytest.mark.unit
def test_the_matrix_covers_both_kinds_of_unconfirmed_entry() -> None:
    """An inference and a rejection are different rows in the store.

    They are also the two halves of the same idea -- evidence was offered for
    this claim and does not stand up -- so a matrix carrying only one of them
    would pin half the rule.
    """
    kinds = set()
    for _, _, citations, _, _ in _MATRIX:
        for entry in citations or []:
            kinds.add("inferred" if entry["tool"] is not None else "rejected")
    assert kinds == {"inferred", "rejected"}


@pytest.mark.unit
def test_an_empty_list_and_a_rejection_differ_over_the_same_empty_tool_list() -> None:
    """The distinction the hand-curated workflow turns on, asserted directly.

    Identical status, identical (empty) tool lists. The ONLY difference is
    whether the store remembers that the model cited something and lost it.
    """
    assert is_pending_review("covered", [], []) is False
    assert is_pending_review("covered", [_rejected("Qradar")], []) is True


@pytest.mark.unit
def test_a_rejection_cannot_be_mistaken_for_a_tool() -> None:
    """A rejected entry applies NO tool, so it must never cancel one out.

    If `uncleared_tools` treated a null `tool` as a name, a rejection would
    remove nothing and the guard would still look like it worked -- until a row
    whose entry happened to carry a tool name for a DIFFERENT field silently
    stopped withholding.
    """
    from app.attack.pending import uncleared_tools

    assert uncleared_tools([_rejected("Qradar")]) == frozenset()
    assert uncleared_tools([_flag("Splunk")]) == frozenset({"Splunk"})


@pytest.mark.unit
def test_a_malformed_entry_raises_rather_than_reading_as_confirmed() -> None:
    """FAIL LOUDLY. Skipping a bad entry would turn unconfirmed evidence into
    confirmed evidence through the error handling of the module written to stop
    exactly that."""
    with pytest.raises(ValueError, match="not an object"):
        is_pending_review("covered", ["Splunk"], ["Splunk"])
    with pytest.raises(ValueError, match="neither null nor a name"):
        is_pending_review("covered", [{"tool": "", "cleared_at": None}], [])
    with pytest.raises(ValueError, match="must be a list or None"):
        is_pending_review("covered", {"tool": "Splunk"}, [])


@pytest.mark.unit
def test_null_and_empty_disagree_for_at_least_one_status() -> None:
    """The tri-state earns its keep only if the two ever differ.

    If NULL and `[]` always produced the same verdict the migration's central
    decision would be inert, and a `nullable=True` column that reads exactly like
    `[]` is the fail-open shape it was written to avoid.
    """
    assert is_pending_review("covered", None, ["Splunk"]) is True
    assert is_pending_review("covered", [], ["Splunk"]) is False
