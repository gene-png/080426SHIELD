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

from app.ai.redact import redact_for_ai, redact_payload
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


@pytest.mark.unit
def test_a_confirmed_citation_retracts_an_earlier_inference_of_the_same_tool() -> None:
    """Citation ORDER must not decide whether a technique scores (#102).

    Found by the §14 audit. `resolve_citations` de-duplicates on the resolved
    name and kept whichever outcome arrived FIRST, so the same two citations
    produced opposite results depending on the order the model happened to list
    them:

    * `["CrowdStrike", "CrowdStrike Falcon"]` -- the substring inference is
      recorded, the later EXACT match is discarded as a duplicate, and the row
      is withheld from the coverage score.
    * `["CrowdStrike Falcon", "CrowdStrike"]` -- the exact match lands first,
      the inference is suppressed, and the row scores.

    While this only fed a display counter it was a curiosity. #102 promoted it
    to a client-facing coverage number, which is the shape CLAUDE.md records as
    a latent quirk made consequential by a later fix.

    A CONFIRMED citation is the strongest evidence available for a capability:
    the model named the approved string exactly, so there is nothing to be wrong
    about. Arriving second makes it no weaker.
    """
    resolver = CitationResolver([Candidate(name="CrowdStrike Falcon")])

    inferred_first = resolve_citations(["CrowdStrike", "CrowdStrike Falcon"], resolver)
    exact_first = resolve_citations(["CrowdStrike Falcon", "CrowdStrike"], resolver)

    assert inferred_first.tools == exact_first.tools == ["CrowdStrike Falcon"]
    assert inferred_first.inferred == [], (
        "an exact citation of the same capability arrived later and did not "
        "retract the inference -- the row is withheld on list order alone"
    )
    assert exact_first.inferred == []
    # The per-citation counters still describe what the MODEL sent: it really
    # did write one name that had to be rescued. Only the row-level record --
    # the thing that decides scoring -- is retracted.
    assert inferred_first.confirmed == exact_first.confirmed == 1
    assert inferred_first.needs_review == exact_first.needs_review == 1
    # And the surfaced tool list must not name a tool with nothing behind it.
    assert inferred_first.needs_review_tools == []


@pytest.mark.unit
def test_an_inference_that_is_never_confirmed_still_stands() -> None:
    """The retraction must not become a guard against recording anything.

    CLAUDE.md: "a guard against DOUBLE-counting will quietly become a guard
    against counting at all." Two different capabilities, one inferred and one
    exact, must leave the inference on record.
    """
    resolver = CitationResolver(
        [Candidate(name="CrowdStrike Falcon"), Candidate(name="Splunk Enterprise")]
    )
    out = resolve_citations(["CrowdStrike", "Splunk Enterprise"], resolver)
    assert out.tools == ["CrowdStrike Falcon", "Splunk Enterprise"]
    assert [e["tool"] for e in out.inferred] == ["CrowdStrike Falcon"]
    assert out.needs_review_tools == ["CrowdStrike Falcon"]


@pytest.mark.unit
def test_a_tool_named_after_the_client_resolves_from_its_redacted_form() -> None:
    """#33 finding 5: the client's own tools were uncitable on every run, forever.

    The resolver is built from the capability list's UNREDACTED names. The
    payload the model sees is redacted inside `run_job`, so a client called
    "Northwind" is shown `[CLIENT] SOC Platform` for a tool stored as
    `Northwind SOC Platform`. The prompt tells the model to cite the name
    verbatim; an obedient model therefore cites a string the resolver has never
    heard of, and the technique it supports reads as uncovered.

    Reproduced on main before this fix:

        stored name         : Northwind SOC Platform
        what the model sees : '[CLIENT] SOC Platform'
        tools applied       : NONE   (rejected: 1)

    That is a client's own MDR contributing zero coverage on every run — and it
    is the largest SYSTEMATIC near miss, because it fires for every tool a client
    named after themselves rather than for an occasional bad guess.

    Resolving it is a CONFIRMATION, not an inference: the placeholder mapping is
    deterministic and ours, not the model's guess. Treating it as needs-review
    would park every client-named tool in the review queue permanently, which is
    the same defect wearing the other hat.
    """
    resolver = CitationResolver(
        [Candidate(name="Northwind SOC Platform", vendor="Northwind")],
        client_org_name="Northwind",
    )

    # The cited string is what the EGRESS PATH produces, not a literal typed
    # here. `redact_payload` is the function `run_job` actually calls, applied to
    # the shape `_capability_payload` actually sends. A hand-written
    # "[CLIENT] SOC Platform" would agree with `_redacted_form` by construction
    # and could never catch the two disagreeing -- which is the ONLY thing this
    # test exists to catch. (CLAUDE.md: derive the expected value from the spec.)
    sent, _ = redact_payload(
        [{"name": "Northwind SOC Platform", "vendor": "Northwind"}],
        mode="strict",
        client_org_name="Northwind",
    )
    cited = sent[0]["name"]
    assert cited != "Northwind SOC Platform", (
        "redaction did not change this name, so the test is not exercising the "
        "defect it is named for"
    )
    out = resolve_citations([cited], resolver)

    assert out.tools == ["Northwind SOC Platform"], (
        "the client's own tool is still uncitable from the only string the model " "was shown"
    )
    assert out.confirmed == 1
    assert out.needs_review == 0 and out.inferred == []
    assert out.rejected == 0


@pytest.mark.unit
def test_the_real_name_still_resolves_when_the_redacted_form_is_indexed() -> None:
    """The guard against fixing one direction by breaking the other.

    A model that cites the stored name — which happens whenever the client's
    name does not appear in the tool, and whenever redaction is off — must keep
    working, and must still be CONFIRMED rather than downgraded.
    """
    resolver = CitationResolver(
        [Candidate(name="Northwind SOC Platform", vendor="Northwind")],
        client_org_name="Northwind",
    )
    out = resolve_citations(["Northwind SOC Platform"], resolver)
    assert out.tools == ["Northwind SOC Platform"]
    assert out.confirmed == 1


@pytest.mark.unit
def test_two_tools_that_redact_to_the_same_string_are_ambiguous_not_guessed() -> None:
    """The invariant this module is built on, applied to the alias tier.

    Reversing a placeholder is only deterministic while it maps to ONE
    candidate. Where it does not, the answer is the same as everywhere else
    here: refuse, count it, and let a human see the string that could not be
    placed.

    The first version of this test asserted the invariant in its NAME and its
    docstring and then used `Northwind Gateway` / `Northwind Secure Gateway`,
    which redact to `[CLIENT] Gateway` and `[CLIENT] Secure Gateway` -- no
    collision at all -- and asserted a SUCCESSFUL resolve. Deleting the
    ambiguity branch left it green. That is #72 exactly, produced in the same
    change that was fixing #72's cousins.

    The collision here is real and comes from the redactor rather than from a
    contrived pair: the address rule over-matches, so `Flowmon` and `Fleet` BOTH
    egress as a bare `[ADDRESS]` (#130). Two distinct capabilities, one shown
    string. Asserted below, from the redactor itself, before the resolver is
    ever consulted -- so if #130 is fixed and the collision disappears, this test
    FAILS LOUDLY rather than quietly passing while testing nothing.
    """
    left, right = "Flowmon", "Fleet"
    a, _ = redact_for_ai(left, mode="strict", client_org_name="Northwind")
    b, _ = redact_for_ai(right, mode="strict", client_org_name="Northwind")
    assert a == b, (
        f"precondition gone: {left!r} and {right!r} no longer redact to the same "
        f"string ({a!r} vs {b!r}). If #130 was fixed, rewrite this test around a "
        f"pair that still collides -- do not delete it."
    )

    resolver = CitationResolver(
        [Candidate(name=left, vendor="Kemp"), Candidate(name=right, vendor="Fleetdm")],
        client_org_name="Northwind",
    )
    out = resolve_citations([a], resolver)

    assert out.tools == [], f"guessed between two capabilities: {out.tools}"
    assert out.rejected == 1
    assert out.confirmed == 0


@pytest.mark.unit
def test_a_real_name_beats_another_capabilitys_redacted_form() -> None:
    """The regression the alias tier exists to prevent, and it is not exotic.

    A client's list can legitimately hold BOTH spellings of one tool. The
    extractor redacts its own inventory input, so before the tenant has a legal
    name it stores `Northwind SOC Platform`, and a later extraction of a
    corrected inventory stores `[CLIENT] SOC Platform`. Both lists contribute,
    and the two strings do not dedupe -- they are not equal casefolded.

    Indexing the alias alongside real names made `[CLIENT] SOC Platform` match
    two candidates, so the ONLY string an obedient model can cite became
    `ambiguous`. Under the #102 withholding rule that then pulls the technique
    out of the coverage denominator entirely -- strictly worse than the defect
    the alias was added to fix.

    A real name is an exact match on what is stored; an alias is a reversal of a
    transformation. When both are available the real name wins.
    """
    resolver = CitationResolver(
        [
            Candidate(name="Northwind SOC Platform", vendor="Northwind"),
            Candidate(name="[CLIENT] SOC Platform", vendor="Northwind"),
        ],
        client_org_name="Northwind",
    )
    out = resolve_citations(["[CLIENT] SOC Platform"], resolver)

    assert out.tools == ["[CLIENT] SOC Platform"], (
        "the stored spelling lost to another capability's alias -- the citation "
        f"resolved to {out.tools} instead of the row that literally matches"
    )
    assert out.confirmed == 1
    assert out.rejected == 0


@pytest.mark.unit
def test_no_client_name_means_no_extra_keys_and_no_behaviour_change() -> None:
    """`client_org_name` is optional, and absent it changes nothing.

    `build_attack_ai_request` passes the client's legal name, but the seeded
    "(pending intake)" placeholder is deliberately passed as None elsewhere in
    this route, so the no-name path is real and must stay inert.
    """
    plain = CitationResolver([Candidate(name="CrowdStrike Falcon", vendor="CrowdStrike")])
    assert resolve_citations(["CrowdStrike Falcon"], plain).tools == ["CrowdStrike Falcon"]
    assert resolve_citations(["[CLIENT] Falcon"], plain).tools == []


@pytest.mark.unit
def test_a_tool_redacted_by_a_rule_other_than_the_org_name_still_resolves() -> None:
    """The alias must reverse the WHOLE redactor, not the org-name rule alone.

    `_redacted_form` originally called `redact_org_name` while its docstring
    claimed to use "the SAME redactor the egress path uses". That was true of one
    rule out of eight, and the difference is not academic: the address rule
    over-matches badly (#130), so `Flowmon` -- a real NDR product, no client name
    in it anywhere -- egresses as a bare `[ADDRESS]`.

    A tool in that state has exactly the #33-finding-5 disease: the only string
    the model is shown is one the resolver has never heard of. Indexing only the
    org-name form left it broken while the docstring said otherwise.

    This test discriminates the two implementations directly, which the
    ambiguity test above does not: with an org-only `_redacted_form` there is no
    alias for `Flowmon` at all, so the citation rejects.
    """
    name = "Flowmon"
    shown, counts = redact_for_ai(name, mode="strict", client_org_name="Northwind")
    assert shown != name and "client_org" not in counts, (
        "precondition gone: this test needs a name rewritten by a NON-org rule, "
        f"got {shown!r} with counts {counts!r}"
    )

    resolver = CitationResolver(
        [Candidate(name=name, vendor="Kemp")],
        client_org_name="Northwind",
    )
    out = resolve_citations([shown], resolver)

    assert out.tools == [name], (
        f"the model was shown {shown!r} and cited it verbatim, and the resolver "
        f"could not place it: {out.tools}"
    )
    assert out.confirmed == 1
    assert out.rejected == 0


@pytest.mark.unit
def test_the_resolver_is_inert_when_the_egress_mode_does_not_redact() -> None:
    """Mode is part of "what the model was shown", not a detail.

    `redact_for_ai` applies the org-name and address rules ONLY in strict mode.
    A resolver hard-coded to strict while the egress ran `standard` would index
    placeholders that were never sent -- inventing aliases for strings the model
    could not have seen. `run_ai` passes the settings value both places.
    """
    lenient = CitationResolver(
        [Candidate(name="Northwind SOC Platform", vendor="Northwind")],
        client_org_name="Northwind",
        redaction_mode="standard",
    )
    assert resolve_citations(["Northwind SOC Platform"], lenient).tools == [
        "Northwind SOC Platform"
    ]
    assert resolve_citations(["[CLIENT] SOC Platform"], lenient).tools == [], (
        "indexed a placeholder the model was never shown -- in standard mode the "
        "org name is not redacted"
    )


@pytest.mark.unit
def test_a_client_built_tools_vendor_resolves_from_its_placeholder() -> None:
    """The vendor half of #33 finding 5, which the first fix left out.

    For a tool the client BUILT, the vendor is the client -- so the payload now
    carries `vendor: "[CLIENT]"` and the prompt names that field. Indexing only
    the unredacted vendor fixed the name half and left this broken, an unstated
    exemption in a fix that read as complete.

    Resolves as an INFERENCE, not confirmed: reversing the placeholder is
    deterministic, but "the model named a vendor" was only ever a guess about
    WHICH tool was meant, and undoing a redaction does not upgrade that.
    """
    resolver = CitationResolver(
        [Candidate(name="SOC Platform", vendor="Northwind")],
        client_org_name="Northwind",
    )
    out = resolve_citations(["[CLIENT]"], resolver)

    assert out.tools == ["SOC Platform"], (
        f"a client-built tool is uncitable by its vendor, which is the only "
        f"vendor string the model is shown: {out.tools}"
    )
    assert out.confirmed == 0, "a vendor match is an inference, not a confirmation"
    assert out.needs_review == 1


@pytest.mark.unit
def test_a_redacted_tool_resolves_even_when_the_client_has_no_legal_name() -> None:
    """Aliasing is conditioned on the REDACTOR, not on the client having a name.

    `_redacted_form` originally returned early when there was no client org name
    and no name hints. But in strict mode the address rule fires regardless of
    both, so a tenant still on "(pending intake)" -- which is precisely when
    `client_org_name` is None -- would have had `Flowmon` egress as `[ADDRESS]`
    with no alias indexed, and the tool uncitable.

    The question is never "is there a name to redact", it is "did the redactor
    change this string".
    """
    shown, _ = redact_for_ai("Flowmon", mode="strict")
    assert shown != "Flowmon", "precondition gone; see #130"

    resolver = CitationResolver([Candidate(name="Flowmon", vendor="Kemp")])
    out = resolve_citations([shown], resolver)
    assert out.tools == [
        "Flowmon"
    ], f"a tenant with no legal name cannot cite its own tool: {out.tools}"
    assert out.confirmed == 1
