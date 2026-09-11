"""An UNUSABLE citation leaves a per-row record, and changes no score (#109).

`resolve_citations` classified a cited entry that is not a usable string -- a
bare string where a list belongs, a null, an empty name -- as `unusable`. It
incremented a run-level counter and emitted nothing into `inferred` or
`rejected_details`, so `_validate_tools` wrote no `row_flags` for it.

The other two no-tool outcomes are persisted per row precisely BECAUSE they name
no tool (`pending.py`, "Three kinds of evidence"). This was the third, and it
had a count and no record.

## The row that loses the disclosure

Scoring is unaffected on a row with no tools at all -- it still gets a
`no_citation` entry and is withheld. The gap is the row that also carries a
usable tool from another field::

    {"technique_code": "T1003", "status": "covered",
     "detection_tools": "CrowdStrike Falcon",     # bare string -- unusable
     "prevention_tools": ["Splunk Enterprise"]}    # fine

`detection_tools` was silently overwritten to `[]`, the run reported
`citations_unusable: 1`, and the row stored "resolved, nothing outstanding".

## Why the scoring assertions are here and not implied

The obvious reading of "one more uncleared entry" is that it withholds the row.
It does not, and that is a property of `is_pending_review`'s case 1 rather than
of anything in this change -- so it is asserted in BOTH directions rather than
left to be inferred, because a future edit to either function could flip it and
a client-facing coverage number is what moves.

Fixture mode cannot reach any of this: `_fixture_mitre_map` always emits
well-formed lists. That is the corollary `CLAUDE.md` already records for
drop/rejection counters, and it is why these are synthetic unit tests.
"""

from __future__ import annotations

import pytest

from app.attack.citations import Resolution, resolve_citations
from app.attack.pending import is_pending_review, uncleared_tools

pytestmark = pytest.mark.unit


class _Resolver:
    """Resolves exactly the names it is given, confirmed, and nothing else.

    Deliberately NOT the production `CitationResolver`. This file is about what
    happens to values the resolver never sees, so building one from the real
    allow-list would couple these assertions to a catalogue that has nothing to
    do with them. It is a stand-in for the WORLD, never for the outcome.

    Structural rather than a subclass: `resolve_citations` takes anything with
    `.resolve(str) -> Resolution`, and inheriting would drag in an `__init__`
    that wants candidates these tests do not have.
    """

    def __init__(self, known: set[str]) -> None:
        self._known = known

    def resolve(self, cited: str) -> Resolution:
        if cited in self._known:
            return Resolution(name=cited, confirmed=True)
        return Resolution(name=None, confirmed=False, rejected_reason="no_match")


def test_a_bare_string_where_a_list_belongs_leaves_a_record() -> None:
    out = resolve_citations("CrowdStrike Falcon", _Resolver({"CrowdStrike Falcon"}))

    assert out.unusable == 1
    assert out.tools == []
    assert out.unusable_details == [{"cited": "CrowdStrike Falcon", "reason": "unusable_field"}], (
        "the string the model actually sent is the part a consultant acts on -- "
        "a bare count says the field was unusable and nothing about what to fix"
    )


def test_a_null_entry_records_no_cited_string_rather_than_the_word_None() -> None:
    out = resolve_citations([None, "Splunk"], _Resolver({"Splunk"}))

    assert out.unusable == 1
    assert out.tools == ["Splunk"]
    assert out.unusable_details == [{"cited": None, "reason": "unusable_entry"}], (
        "`str(None)` would put the word 'None' in the consultant's queue as "
        "though the model had written it"
    )


def test_the_two_unusable_shapes_are_not_collapsed() -> None:
    """A wrong-shaped FIELD and a bad ITEM are different things to fix.

    `unusable` counts both and cannot tell them apart, which is fine for a
    count. The record is what a consultant works from, so it says which.
    """
    field_level = resolve_citations("Falcon", _Resolver(set()))
    entry_level = resolve_citations(["", 7], _Resolver(set()))

    assert [e["reason"] for e in field_level.unusable_details] == ["unusable_field"]
    assert [e["reason"] for e in entry_level.unusable_details] == [
        "unusable_entry",
        "unusable_entry",
    ]
    assert entry_level.unusable == 2


def test_an_empty_list_is_not_unusable() -> None:
    """THE PASSING STATE, and the one that would make the record noise.

    An empty list is the model saying it cites nothing for this field. Recording
    that as unusable would queue a consultant to review a non-event, and
    `no_citation` is the mechanism that already covers a claim with no evidence.
    """
    out = resolve_citations([], _Resolver(set()))
    assert out.unusable == 0
    assert out.unusable_details == []


def test_an_explicit_null_is_unusable_and_is_NOT_an_omitted_key() -> None:
    """Split from the case above, which charged them differently and called them
    "the same case" in a comment directly over the assertion that distinguishes
    them.

    An OMITTED key never reaches here at all -- `_validate_tools` is called only
    `if tool_field in sugg` -- so a `None` arriving means the model sent an
    explicit JSON null, which is a shape the prompt did not ask for. The earlier
    comment would have sent a maintainer hunting a double-charge for omitted
    keys that cannot happen.
    """
    out = resolve_citations(None, _Resolver(set()))
    assert out.unusable == 1
    assert out.unusable_details == [{"cited": None, "reason": "unusable_field"}]


def test_a_clean_list_records_nothing() -> None:
    out = resolve_citations(["Splunk"], _Resolver({"Splunk"}))
    assert out.unusable == 0
    assert out.unusable_details == []
    assert out.tools == ["Splunk"]


# ---------------------------------------------------------------------------
# The scoring half. Both directions, because the obvious reading is wrong.
# ---------------------------------------------------------------------------


def _entry(**over: object) -> dict:
    base = {"tool": None, "cited": None, "reason": "unusable_field", "field": "detection_tools"}
    base.update(over)
    base.setdefault("cleared_at", None)
    return base


def test_an_unusable_entry_does_not_withhold_a_row_a_real_tool_backs() -> None:
    """The issue's own scenario, and the property that makes this safe.

    `detection_tools` was malformed; `prevention_tools` named a tool that
    resolved. The claim is backed, so the row must still score -- and the
    disclosure must still be on record. Before #109 the second half was missing;
    a fix that withheld the row instead would have traded one defect for a
    client-facing coverage drop.
    """
    citations = [_entry(cited="CrowdStrike Falcon")]

    assert uncleared_tools(citations) == frozenset(), (
        "an entry with `tool: None` must never reach `uncleared_tools` -- a "
        "rejection that could pass for a tool name would cancel out a real one"
    )
    assert (
        is_pending_review("covered", citations, ["Splunk Enterprise"]) is False
    ), "a confirmed tool backs the claim; case 1 returns before the evidence check"


def test_an_unusable_entry_does_not_rescue_a_row_with_no_tools_either() -> None:
    """The other direction. A row with nothing to stand on stays withheld.

    Asserting only the test above would pass against an implementation that
    made `has_uncleared_evidence` blind to these entries -- which would be a
    fail-OPEN on the row the issue says is already handled correctly.
    """
    citations = [_entry(cited=None, reason="unusable_entry")]
    assert is_pending_review("covered", citations, []) is True


def test_a_row_nobody_cited_anything_for_is_still_left_alone() -> None:
    """Case 3, unchanged, and it is the one a hand-curating consultant is in.

    `test_heatmap_reflects_coverage_after_patches` predates the feature and
    caught this once already: ten techniques set to `covered` by hand reported
    zero covered. An empty list must stay "resolved, nothing outstanding".
    """
    assert is_pending_review("covered", [], ["Splunk Enterprise"]) is False
    assert is_pending_review("covered", [], []) is False
