"""W2: resolving a model's tool citation, against an invariant that has to hold.

`main` validates cited tools with exact lowercase match (`t.lower() in
valid_tools`) and drops every near miss SILENTLY — no count, no reason. The
technique keeps whatever status the model gave it, so a citation that missed by
a word leaves a technique reading `covered` with an empty tool list, or reads as
`gap` when the client owns the control. A fabricated gap is exactly the failure
N-033 shipped (607 of them, from `tools_available: 0`).

PR #29 built a resolver for this and it was patched twice, each patch looking
done and each wrong, both found only by adversarial audit while CI stayed green.
Its stated invariant — "every rule either finds EXACTLY ONE candidate or gives
up" — never held. This is written fresh against that invariant rather than
ported, with all four known-broken paths as named test cases:

1. the nullable-vendor bypass (one blank vendor and the original bug returns)
2. name-vs-vendor cross ambiguity, unchecked
3. the substring rule not refusing on 2+ matches — it fell through to the vendor
   rule, which resolved anyway
4. #11, the fold asymmetry: `_fold(name) != cited.strip().casefold()` folded the
   left side and not the right, so a VERBATIM citation of any punctuated name
   was reported as normalised. Harmless as log noise; #29 then surfaced the
   counter, turning it into a false statement a consultant can act on.

Three outcomes, per the tri-state settled on #30 and 5.1:

* CONFIRMED — matched with no inference (case and whitespace only). Nothing to
  be wrong about.
* NEEDS_REVIEW — resolved, but the resolver had to CHANGE something to make it
  match. Inference is not confirmation however plausible. Applied and visible,
  but queued for a human.
* REJECTED — no unique resolution. Counted and visible; the citation is gone.

The accuracy tiebreak, from the plan: "A dropped citation is counted and
visible. A wrong attribution is invisible and reaches the client." So ambiguity
rejects rather than guesses.
"""

from __future__ import annotations

import pytest

from app.attack.citations import (
    Candidate,
    CitationResolver,
    ReviewReason,
    resolve_citations,
)


def _r(*candidates: tuple[str, str | None]) -> CitationResolver:
    return CitationResolver([Candidate(name=n, vendor=v) for n, v in candidates])


# --- CONFIRMED: no inference ------------------------------------------------


@pytest.mark.unit
def test_an_exact_citation_is_confirmed() -> None:
    res = _r(("Splunk Enterprise", "Splunk")).resolve("Splunk Enterprise")
    assert (res.name, res.confirmed, res.review_reason) == ("Splunk Enterprise", True, None)


@pytest.mark.unit
def test_case_and_whitespace_differences_are_still_confirmed() -> None:
    """Normalising case and whitespace infers nothing — the plan draws the line
    here explicitly, and drawing it wider reports 0% coverage on every fresh run
    until a consultant walks all 633 techniques."""
    res = _r(("Splunk Enterprise", None)).resolve("  splunk   ENTERPRISE ")
    assert res.name == "Splunk Enterprise"
    assert res.confirmed is True


@pytest.mark.unit
def test_a_verbatim_punctuated_citation_is_confirmed_not_normalised() -> None:
    """#11. `Tenable.io` cited exactly was reported as a near miss.

    The old comparison folded the candidate name and only case-folded the
    citation, so any punctuated name could never compare equal to itself. Once
    #29 surfaced the counter, a client with punctuation in a tool name saw a
    permanently non-zero near-miss count with zero near misses.
    """
    for name in ("Tenable.io", "AT&T Cybersecurity", "F5 BIG-IP"):
        res = _r((name, None)).resolve(name)
        assert res.name == name
        assert res.confirmed is True, f"{name!r} cited verbatim was called an inference"
        assert res.review_reason is None


# --- NEEDS_REVIEW: resolved, but by inference -------------------------------


@pytest.mark.unit
def test_a_punctuation_only_difference_needs_review() -> None:
    """`Tenable io` for `Tenable.io` IS a change the resolver made. It is very
    likely right, and it is still an inference — 5.1 is explicit that plausible
    is not confirmed."""
    res = _r(("Tenable.io", None)).resolve("Tenable io")
    assert res.name == "Tenable.io"
    assert res.confirmed is False
    assert res.review_reason == ReviewReason.PUNCTUATION


@pytest.mark.unit
def test_a_distinct_substring_needs_review() -> None:
    res = _r(("CrowdStrike Falcon Enterprise", "CrowdStrike")).resolve("CrowdStrike")
    assert res.name == "CrowdStrike Falcon Enterprise"
    assert res.confirmed is False


@pytest.mark.unit
def test_a_substring_must_respect_word_boundaries() -> None:
    """ "Okta" must not resolve via "Diagnostokta"."""
    assert _r(("Diagnostokta Suite", None)).resolve("Okta").name is None


@pytest.mark.unit
def test_a_unique_vendor_needs_review() -> None:
    res = _r(("Falcon", "CrowdStrike"), ("Splunk ES", "Splunk")).resolve("CrowdStrike")
    assert res.name == "Falcon"
    assert res.confirmed is False
    assert res.review_reason == ReviewReason.VENDOR


# --- the four known-broken paths -------------------------------------------


@pytest.mark.unit
def test_defect_1_a_blank_vendor_does_not_let_a_confident_attribution_through() -> None:
    """One blank vendor and the original bug returns.

    `Duo Security` may well be Cisco's; the list simply does not say. The vendor
    index only held candidates WITH a vendor, so the ambiguity check saw one
    Cisco product and waved it through. Uniqueness cannot be established from
    the data present, so this is an inference at best — never confident.
    """
    res = _r(("Cisco Umbrella", "Cisco"), ("Duo Security", None)).resolve("Cisco")
    assert res.confirmed is False
    assert res.review_reason == ReviewReason.INCOMPLETE_VENDOR_DATA, (
        "resolved as though the vendor data were complete — the case that "
        "credited a DNS filter with Duo's brute-force prevention"
    )


@pytest.mark.unit
def test_defect_2_name_vs_vendor_cross_ambiguity_is_refused() -> None:
    """`VMware` names one capability and vends another.

    Checking the two indexes separately found exactly one match in each and
    resolved to the NAME, so citing "VMware" credited Carbon Black with whatever
    Workspace ONE provides. The candidate sets must be UNIONED before uniqueness
    is judged.
    """
    res = _r(("VMware Carbon Black", "Broadcom"), ("Workspace ONE", "VMware")).resolve("VMware")
    assert res.name is None, "resolved across a name/vendor cross"
    assert res.rejected_reason == "ambiguous"


@pytest.mark.unit
def test_defect_3_two_substring_matches_refuse_instead_of_falling_through() -> None:
    """The substring rule returned only when it found exactly one — and then
    fell through to the vendor rule, which resolved anyway. Two candidates is
    not a reason to try a different rule; it is a reason to stop."""
    # NO vendors. The first version gave both candidates the vendor "Splunk", so
    # `by_vendor` alone already held two names and the union was ambiguous
    # regardless — deleting `by_substring` entirely left this test green. It was
    # named after defect 3 and could not detect defect 3. Instance eleven of #72.
    res = _r(
        ("Splunk Enterprise", None),
        ("Splunk Phantom", None),
    ).resolve("Splunk")
    assert res.name is None, "two substring matches resolved anyway"
    assert res.rejected_reason == "ambiguous"


@pytest.mark.unit
def test_two_substring_matches_are_refused_even_when_a_vendor_could_resolve_one() -> None:
    """The original fall-through, exactly: the substring rule found two, gave up,
    and the vendor rule then resolved one of them anyway."""
    res = _r(
        ("Splunk Enterprise", "Splunk"),
        ("Splunk Phantom", None),
    ).resolve("Splunk")
    assert res.name is None
    assert res.rejected_reason == "ambiguous"


@pytest.mark.unit
def test_an_unknown_citation_is_rejected_not_guessed() -> None:
    res = _r(("Splunk Enterprise", "Splunk")).resolve("Qradar")
    assert res.name is None
    assert res.rejected_reason == "unknown"


@pytest.mark.unit
def test_two_capabilities_differing_only_by_punctuation_are_refused() -> None:
    """Refusing to guess between them is the invariant working."""
    res = _r(("Tenable.io", None), ("Tenable io", None)).resolve("Tenable-io")
    assert res.name is None
    assert res.rejected_reason == "ambiguous"


# --- accounting -------------------------------------------------------------


@pytest.mark.unit
def test_every_cited_string_lands_in_exactly_one_bucket() -> None:
    """The W1 discipline, applied here: a surfaced number that does not add up
    is worse than no number."""
    resolver = _r(
        ("Splunk Enterprise", "Splunk"),
        ("Tenable.io", None),
        ("Cisco Umbrella", "Cisco"),
        ("Duo Security", None),
    )
    cited = ["Splunk Enterprise", "Tenable io", "Cisco", "Qradar", "Splunk Enterprise"]
    out = resolve_citations(cited, resolver)
    assert out.confirmed + out.needs_review + out.rejected == len(cited)


@pytest.mark.unit
def test_duplicate_citations_collapse_to_one_tool() -> None:
    """Naming both "CrowdStrike" and "CrowdStrike Falcon Enterprise" means one
    tool; recording it twice would overstate coverage."""
    resolver = _r(("CrowdStrike Falcon Enterprise", "CrowdStrike"))
    out = resolve_citations(["CrowdStrike", "CrowdStrike Falcon Enterprise"], resolver)
    assert out.tools == ["CrowdStrike Falcon Enterprise"]


@pytest.mark.unit
def test_needs_review_tools_are_reported_separately_from_the_applied_list() -> None:
    """5.1: flagged is retained and visible, not dropped. The consultant needs
    to know WHICH tools are unconfirmed, not just how many."""
    resolver = _r(("Tenable.io", None), ("Splunk Enterprise", "Splunk"))
    out = resolve_citations(["Splunk Enterprise", "Tenable io"], resolver)
    assert out.tools == ["Splunk Enterprise", "Tenable.io"]
    assert out.needs_review_tools == ["Tenable.io"]


@pytest.mark.unit
def test_rejected_examples_are_captured_verbatim_and_bounded() -> None:
    """Verbatim is the point: "GV.OC-1" tells you the catalogue holds
    "GV.OC-01". A bare count tells you nothing."""
    resolver = _r(("Splunk Enterprise", None))
    out = resolve_citations([f"Bogus {i}" for i in range(12)], resolver)
    assert out.rejected == 12
    assert out.rejected_examples[0] == "Bogus 0"
    assert len(out.rejected_examples) <= 5


@pytest.mark.unit
def test_a_non_list_payload_yields_nothing_rather_than_iterating_a_string() -> None:
    resolver = _r(("Splunk Enterprise", None))
    out = resolve_citations("Splunk Enterprise", resolver)
    assert out.tools == []
    assert out.confirmed == out.needs_review == out.rejected == 0
    # Counted, not silent. The row's tools get overwritten with [] either way,
    # so reporting "the model cited nothing" would be a lie about a shape drift.
    # The first version of this test asserted the silence was correct.
    assert out.unusable == 1


@pytest.mark.unit
def test_blank_and_non_string_citations_are_ignored_not_counted() -> None:
    resolver = _r(("Splunk Enterprise", None))
    out = resolve_citations(["", "   ", None, 42], resolver)
    assert out.tools == []
    assert out.confirmed == out.needs_review == out.rejected == 0
    assert out.unusable == 4, "unusable entries were discarded without a count"


@pytest.mark.unit
def test_the_review_reason_reaches_the_outcome() -> None:
    """Defect 1's guard was INERT until this existed.

    `resolve` computed `INCOMPLETE_VENDOR_DATA` and nothing read it —
    `resolve_citations` branched only on `name is None` and `confirmed`, so
    deleting the guard changed no observable behaviour and `test_defect_1` was
    green over a defect that still shipped. A vendor guess made against a list
    with missing vendors must not report identically to a punctuation rescue.
    """
    resolver = _r(("Cisco Umbrella", "Cisco"), ("Duo Security", None), ("Tenable.io", "Tenable"))
    out = resolve_citations(["Cisco", "Tenable io"], resolver)
    assert out.needs_review == 2
    assert out.needs_review_by_reason["incomplete_vendor_data"] == ["Cisco Umbrella"]
    assert out.needs_review_by_reason["punctuation"] == ["Tenable.io"]
