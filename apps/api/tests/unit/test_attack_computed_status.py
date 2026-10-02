"""#554 R3: an ATT&CK technique's status is computed from Detect / Prevent / Respond.

The decisions, relayed by the advisor on #554 (2026-10-02):

* Covered only when Detect, Prevent and Respond are all in place; any other
  combination is Partial; nothing in any of the three is a Gap.
* "In place" (Q1, c1): at least one listed tool whose citation is not pending
  review -- `pending.py`'s definition, an exact name match included.
* A technique MITRE lists no preventive control for (Q2) is judged on Detect
  and Respond, and is Covered when both are in place (Q3).
* An "awaiting review" capability is scored at the LOWER bound, as not in place
  (Q4), and the display still says "awaiting review".
* Retirement is ignored: this is the "today" figure (Q5); #801 adds "after".

THE EXPECTED VALUES COME FROM THE TABLE POSTED ON #554 (comment 5961953360),
written as Y / N / U counts, never from the module under test: the matrix is
written out below and every one of the 27 + 9 combinations is driven through
real rows.
"""

from __future__ import annotations

import itertools
from types import SimpleNamespace

import pytest

from app.attack import computed
from app.attack.pending import pending_codes

pytestmark = pytest.mark.unit

#: A preventable leaf with no sub-techniques, and one MITRE lists no
#: preventive control for (T1082, System Information Discovery). Facts about
#: ATT&CK 19.2, pinned in test_attack_not_preventable.py.
PREVENTABLE = "T1003.001"
UNPREVENTABLE = "T1082"

#: The posted table, preventable: (in place, not in place, awaiting) -> status.
#: The undetermined classes are at their lower bound (Q4).
PREVENTABLE_TABLE = {
    (3, 0, 0): "covered",
    (0, 3, 0): "gap",
    (2, 1, 0): "partial",
    (1, 2, 0): "partial",
    (1, 1, 1): "partial",
    (2, 0, 1): "partial",  # Covered or Partial -> Partial
    (1, 0, 2): "partial",  # Covered or Partial -> Partial
    (0, 2, 1): "gap",  # Gap or Partial -> Gap
    (0, 1, 2): "gap",
    (0, 0, 3): "gap",
}
#: The posted table, cannot be prevented: Detect and Respond only.
UNPREVENTABLE_TABLE = {
    (2, 0, 0): "covered",
    (0, 2, 0): "gap",
    (1, 1, 0): "partial",
    (1, 0, 1): "partial",  # Covered or Partial -> Partial
    (0, 1, 1): "gap",  # Gap or Partial -> Gap
    (0, 0, 2): "gap",
}


def _row(code: str, d: str, p: str, r: str, *, status: str = "partial", reviewed=None):
    """A stored row whose three capabilities are Y (a confirmed tool), N (no
    tool) or U (a tool whose citation is awaiting a human)."""
    citations: list[dict] = []
    lists: dict[str, list[str]] = {}
    for field, value in (("detection_tools", d), ("prevention_tools", p), ("response_tools", r)):
        if value == "Y":
            lists[field] = [f"{field}-confirmed"]
        elif value == "U":
            name = f"{field}-inferred"
            lists[field] = [name]
            citations.append({"tool": name, "cited": name, "reason": "inferred", "cleared_at": None})
        else:
            lists[field] = []
    return SimpleNamespace(
        technique_code=code,
        status=status,
        reason_code=None,
        unconfirmed_citations=citations,
        reviewed_status=reviewed,
        **lists,
    )


_DRAFT = SimpleNamespace(id="a", status_rules=None, parent_rules=None)
_STORED = SimpleNamespace(id="b", status_rules=1, parent_rules=1)


def _counts(values: tuple[str, ...]) -> tuple[int, ...]:
    return (values.count("Y"), values.count("N"), values.count("U"))


@pytest.mark.parametrize("dpr", list(itertools.product("YNU", repeat=3)), ids="".join)
def test_every_preventable_combination(dpr) -> None:
    (row,) = computed.effective_coverage(_DRAFT, [_row(PREVENTABLE, *dpr)])
    assert row.status == PREVENTABLE_TABLE[_counts(dpr)]


@pytest.mark.parametrize("dpr", list(itertools.product("YNU", repeat=3)), ids="".join)
def test_every_unpreventable_combination_ignores_prevention(dpr) -> None:
    """Whatever the Prevent list holds, it is not judged: MITRE lists no
    preventive control, so the line reads "cannot be prevented"."""
    (row,) = computed.effective_coverage(_DRAFT, [_row(UNPREVENTABLE, *dpr)])
    d, _, r = dpr
    assert row.status == UNPREVENTABLE_TABLE[_counts((d, r))]
    assert row.capabilities.prevent is computed.InPlace.CANNOT_BE_PREVENTED


@pytest.mark.parametrize("dpr", list(itertools.product("YNU", repeat=3)), ids="".join)
def test_nothing_is_withheld_for_pending_review_on_a_computed_assessment(dpr) -> None:
    """Q4: an unconfirmed tool does not count, so a computed status never rests
    on unconfirmed evidence and `pending_codes` has nothing to withhold. The
    disclosure sentence carries the count instead."""
    rows = computed.effective_coverage(_DRAFT, [_row(PREVENTABLE, *dpr)])
    assert pending_codes(rows, parents_computed=True) == frozenset()


def test_the_line_is_the_approved_copy() -> None:
    (row,) = computed.effective_coverage(_DRAFT, [_row(PREVENTABLE, "Y", "N", "U")])
    assert row.capabilities.line() == (
        "Detect: in place · Prevent: not in place · Respond: awaiting review"
    )
    (row,) = computed.effective_coverage(_DRAFT, [_row(UNPREVENTABLE, "Y", "Y", "Y")])
    assert row.capabilities.line() == (
        "Detect: in place · Prevent: cannot be prevented · Respond: in place"
    )


def test_never_resolved_citations_are_awaiting_review() -> None:
    """NULL citations mean nobody checked the tools (migration 0044): absence of
    evidence is not confirmation."""
    row = _row(PREVENTABLE, "Y", "Y", "Y")
    row.unconfirmed_citations = None
    (eff,) = computed.effective_coverage(_DRAFT, [row])
    assert eff.status == "gap"
    assert eff.capabilities.awaiting


def test_a_cleared_citation_is_in_place_and_a_rejected_one_changes_nothing() -> None:
    row = _row(PREVENTABLE, "U", "Y", "Y")
    row.unconfirmed_citations[0]["cleared_at"] = "2026-10-02T00:00:00Z"
    # A rejected citation resolved to no tool: it names nothing on the lists.
    row.unconfirmed_citations.append(
        {"tool": None, "cited": "Unknown thing", "reason": "rejected_unknown", "cleared_at": None}
    )
    (eff,) = computed.effective_coverage(_DRAFT, [row])
    assert eff.status == "covered"
    assert not eff.capabilities.awaiting


def test_one_confirmed_tool_puts_a_capability_in_place_beside_an_inferred_one() -> None:
    row = _row(PREVENTABLE, "Y", "Y", "Y")
    row.detection_tools.append("also-inferred")
    row.unconfirmed_citations.append({"tool": "also-inferred", "cleared_at": None})
    (eff,) = computed.effective_coverage(_DRAFT, [row])
    assert eff.status == "covered"
    assert eff.capabilities.detect is computed.InPlace.IN_PLACE


@pytest.mark.parametrize("stored", ["not_applicable", None])
def test_a_ruling_or_an_unscored_row_is_not_computed(stored) -> None:
    """N/A is a consultant's ruling, and an unscored row is an absence nobody
    assessed: computing either would overwrite a fact with a guess."""
    (eff,) = computed.effective_coverage(_DRAFT, [_row(PREVENTABLE, "Y", "Y", "Y", status=stored)])
    assert eff.status == stored
    assert eff.capabilities is None


def test_an_assessment_approved_before_r3_reads_its_stored_statuses() -> None:
    rows = [_row(PREVENTABLE, "Y", "Y", "Y", status="partial")]
    (eff,) = computed.effective_coverage(_STORED, rows)
    assert eff is rows[0]
    assert eff.status == "partial"


def test_a_parent_is_computed_from_its_childrens_computed_statuses() -> None:
    """T1003's children: one computed Covered and the rest Gap make a Partial
    parent, whatever the parent's own stored status says (#620)."""
    from app.attack.parents import PARENT_CHILDREN

    kids = PARENT_CHILDREN["T1003"]
    rows = [_row(kids[0], "Y", "Y", "Y", status="gap")]
    rows += [_row(k, "N", "N", "N", status="covered") for k in kids[1:]]
    rows.append(_row("T1003", "Y", "Y", "Y", status="covered"))
    by_code = {r.technique_code: r for r in computed.effective_coverage(_DRAFT, rows)}
    assert by_code[kids[0]].status == "covered"
    assert {by_code[k].status for k in kids[1:]} == {"gap"}
    assert by_code["T1003"].status == "partial"
    assert by_code["T1003"].capabilities is None


def test_the_suggestion_is_the_stored_status() -> None:
    (eff,) = computed.effective_coverage(_DRAFT, [_row(PREVENTABLE, "Y", "Y", "Y")])
    assert (eff.status, eff.suggested_status) == ("covered", "partial")


def test_awaiting_counts_rows_with_a_capability_awaiting_review() -> None:
    rows = computed.effective_coverage(
        _DRAFT,
        [
            _row("T1003.001", "Y", "U", "Y"),
            _row("T1003.002", "U", "U", "U"),
            _row("T1003.003", "Y", "Y", "Y"),
            _row("T1003.004", "U", "U", "U", status="not_applicable"),
        ],
    )
    assert computed.awaiting_review_count(rows) == 2


def test_the_review_queue() -> None:
    """A row is awaiting review when its computed status differs from the stored
    suggestion and no review accepted THAT computed status. A review of an older
    computed status does not carry over."""
    rows = computed.effective_coverage(
        _DRAFT,
        [
            _row("T1003.001", "Y", "Y", "Y", status="partial"),  # differs, unreviewed
            _row("T1003.002", "Y", "Y", "Y", status="partial", reviewed="covered"),  # reviewed
            _row("T1003.003", "Y", "N", "Y", status="gap", reviewed="covered"),  # moved since
            _row("T1003.004", "Y", "Y", "Y", status="covered"),  # agrees
            _row("T1003.005", "Y", "Y", "Y", status="not_applicable"),  # a ruling
        ],
    )
    assert computed.review_queue(rows) == ("T1003.001", "T1003.003")


def test_parents_are_never_in_the_review_queue() -> None:
    from app.attack.parents import PARENT_CHILDREN

    kids = PARENT_CHILDREN["T1003"]
    rows = [_row(k, "Y", "Y", "Y", status="covered") for k in kids]
    rows.append(_row("T1003", "N", "N", "N", status="gap"))
    assert computed.review_queue(computed.effective_coverage(_DRAFT, rows)) == ()


def test_an_assessment_approved_before_r3_has_no_queue_and_nothing_awaiting() -> None:
    rows = computed.effective_coverage(_STORED, [_row(PREVENTABLE, "U", "U", "U")])
    assert computed.review_queue(rows) == ()
    assert computed.awaiting_review_count(rows) == 0
