"""Resolving a model's tool citation to the client's approved capability.

The failure this prevents: an exact-match check dropped a near-miss citation
SILENTLY, so the technique it was meant to cover read as a gap. In a client
report "gap" then means "the model phrased the name wrong", which is
indistinguishable from "the client has no control here" — and a fabricated gap is
what N-033 shipped.

The opposite failure matters just as much. Attributing a control to the WRONG
tool is worse than dropping the citation: a drop is counted and visible, a wrong
attribution is invisible. So every rule below either finds exactly one candidate
or gives up.
"""

from __future__ import annotations

import pytest

from app.attack.citations import Candidate, CitationResolver, resolve_citations


def _resolver(*candidates: Candidate) -> CitationResolver:
    return CitationResolver(list(candidates))


@pytest.mark.unit
def test_exact_citation_resolves_and_is_not_counted_as_normalised() -> None:
    r = _resolver(Candidate("CrowdStrike Falcon Enterprise", "CrowdStrike"))
    assert r.resolve("CrowdStrike Falcon Enterprise") == (
        "CrowdStrike Falcon Enterprise",
        False,
    )


@pytest.mark.unit
def test_case_and_whitespace_differences_resolve() -> None:
    r = _resolver(Candidate("Splunk Enterprise Security"))
    name, normalised = r.resolve("  splunk   enterprise security ")
    assert name == "Splunk Enterprise Security"
    assert normalised is True


@pytest.mark.unit
def test_punctuation_differences_resolve() -> None:
    """ "Tenable io" is the same product as "Tenable.io"."""
    r = _resolver(Candidate("Tenable.io"))
    assert r.resolve("Tenable io")[0] == "Tenable.io"


@pytest.mark.unit
def test_a_vendor_only_citation_resolves_when_one_tool_matches() -> None:
    """The exact case the repo owner raised, and the one enrichment makes likelier.

    Handing the model `vendor` gives it a plausible string that is not the name.
    """
    r = _resolver(Candidate("CrowdStrike Falcon Enterprise", "CrowdStrike"))
    name, normalised = r.resolve("CrowdStrike")
    assert name == "CrowdStrike Falcon Enterprise"
    assert normalised is True


@pytest.mark.unit
def test_a_partial_name_resolves_when_only_one_capability_contains_it() -> None:
    r = _resolver(Candidate("Microsoft Defender for Endpoint"), Candidate("Okta"))
    assert r.resolve("Defender")[0] == "Microsoft Defender for Endpoint"


@pytest.mark.unit
def test_an_ambiguous_partial_is_refused_rather_than_guessed() -> None:
    """Two plausible homes means we do not know. Dropping is the honest answer.

    Edit-distance matching would rank these equally and silently pick one; that
    is a wrong attribution, which is invisible in the report.
    """
    r = _resolver(
        Candidate("Microsoft Defender for Endpoint"),
        Candidate("Microsoft Defender for Cloud"),
    )
    assert r.resolve("Microsoft Defender") == (None, False)


@pytest.mark.unit
def test_an_ambiguous_vendor_is_refused() -> None:
    """Two products, one vendor: the citation could mean either, so refuse.

    NOTE the candidate names. This test previously used "Splunk Enterprise
    Security" + "Splunk Phantom" — BOTH containing "Splunk" — so the substring
    rule saw two matches and refused, and the vendor rule was never reached. It
    passed while proving nothing about vendor ambiguity, which is the case it is
    named for. Only ONE name may embed the vendor, or the test cannot see the
    rule it is testing.
    """
    r = _resolver(
        Candidate("Splunk Enterprise Security", "Splunk"),
        Candidate("Phantom SOAR", "Splunk"),
    )
    assert r.resolve("Splunk") == (None, False)


@pytest.mark.unit
def test_a_vendor_shared_by_two_products_is_refused_even_when_only_one_is_named_for_it() -> None:
    """The real-world shape: Cisco sells both a DNS filter and an MFA product.

    Resolving "Cisco" to Umbrella would credit a DNS filter with brute-force
    prevention that actually comes from Duo — a wrong attribution, which is
    invisible in a report, and which would be counted as a NORMALISED success
    rather than a refusal.
    """
    r = _resolver(
        Candidate("Cisco Umbrella", "Cisco"),
        Candidate("Duo Security", "Cisco"),
    )
    assert r.resolve("Cisco") == (None, False)


@pytest.mark.unit
def test_substring_matching_respects_word_boundaries() -> None:
    """ "Okta" must not resolve through an unrelated word that contains it."""
    r = _resolver(Candidate("Diagnostoktavia Suite"))
    assert r.resolve("Okta") == (None, False)


@pytest.mark.unit
def test_an_unknown_tool_is_still_refused() -> None:
    """The allow-list is the point: a tool the client does not own is never cited."""
    r = _resolver(Candidate("Splunk Enterprise Security", "Splunk"))
    assert r.resolve("Palo Alto Cortex XDR") == (None, False)


@pytest.mark.unit
def test_two_citations_of_one_tool_collapse() -> None:
    """The model naming both the vendor and the product means ONE tool.

    Recording it twice would overstate coverage.
    """
    r = _resolver(Candidate("CrowdStrike Falcon Enterprise", "CrowdStrike"))
    out = resolve_citations(["CrowdStrike", "CrowdStrike Falcon Enterprise"], r)
    assert out.tools == ["CrowdStrike Falcon Enterprise"]
    assert out.normalised == 1


@pytest.mark.unit
def test_unresolved_citations_are_counted_and_sampled() -> None:
    """The backstop. Genuinely unresolvable citations must not vanish quietly."""
    r = _resolver(Candidate("Splunk Enterprise Security"))
    out = resolve_citations(["Nonexistent Tool", "Also Fake"], r)
    assert out.tools == []
    assert out.rejected == 2
    assert out.rejected_examples == ["Nonexistent Tool", "Also Fake"]


@pytest.mark.unit
def test_non_list_and_non_string_input_is_survivable() -> None:
    r = _resolver(Candidate("Splunk"))
    assert resolve_citations("not a list", r).tools == []
    assert resolve_citations([None, 42, "Splunk"], r).tools == ["Splunk"]


@pytest.mark.unit
def test_the_real_collision_on_the_validation_client() -> None:
    """A live case, not a hypothetical.

    `UX-E2E-Validation-20260807-1332` carries an approved v1 AND a draft v2 from
    malformed-upload testing, and BOTH feed the allow-list — so the bare vendor
    stub and the full product name are both citable:

        v1 APPROVED  CrowdStrike Falcon Enterprise
        v2 DRAFT     CrowdStrike

    A citation of "CrowdStrike" therefore matches EXACTLY and must resolve to the
    stub, not be re-pointed at the approved product. Resolution must never
    override an exact hit — that would be the code overruling the data.
    """
    r = _resolver(
        Candidate("CrowdStrike Falcon Enterprise", "CrowdStrike"),
        Candidate("CrowdStrike"),
    )
    assert r.resolve("CrowdStrike") == ("CrowdStrike", False)
    assert r.resolve("CrowdStrike Falcon Enterprise")[0] == "CrowdStrike Falcon Enterprise"
