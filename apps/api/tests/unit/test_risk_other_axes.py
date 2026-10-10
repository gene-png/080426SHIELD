"""#806 Risk record, build requirement 2 (G1 option 3): `other_axes`.

The approved text: "`other_axes` lists every other axis the scenario also
directly affects (empty when none)", "never repeats `axis`, has no duplicates,
and is ordered detection, prevention, response", each value one of the `axis`
tokens. The record: the parser validates each element and DROPS AND COUNTS an
invalid token, a duplicate, or the primary axis repeated; `axis_counts` and
`entries_without_axis` stay primary-only (#313 arithmetic).

Driven through the generate route with a hand-built model response (fixture
mode echoes the parser's own vocabulary, so it cannot produce a drop) and read
back through the API a consultant reaches. Expected values are written from the
approved text, never from the parser.
"""

from __future__ import annotations

import json

import pytest

from app.ai.llm import LLMResponse

from .test_risk_register import (
    _admin,
    _generated_audit,
    _seed_attack_and_zt,
    app_client,  # noqa: F401  -- the fixture, used by name below.
)

pytestmark = pytest.mark.unit


def _entry(source_id: str, **over: object) -> dict:
    e: dict[str, object] = {
        "title": "Credential theft exposure",
        "description": "d",
        "axis": "detection",
        "source": "coverage_finding",
        "source_id": source_id,
        "linked_techniques": [],
        "linked_controls": [],
        "likelihood": "high",
        "impact": "major",
        "compensating_controls": "None identified in the supplied information.",
        "residual_risk": "r",
        "recommended_action": "remediate",
        "rationale": "r",
    }
    e.update(over)
    return e


def _generate(app_client, entries_for) -> tuple[dict, dict]:  # noqa: F811
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, capability = _seed_attack_and_zt(c, bearer, cid)
    provider.register_static(
        "risk_synthesize",
        LLMResponse(json.dumps({"entries": entries_for(technique, capability)})),
    )
    r = c.post(
        f"/risk/clients/{cid}/register/generate", headers={"Authorization": f"Bearer {bearer}"}
    )
    assert r.status_code == 201, r.text
    latest = c.get(
        f"/risk/clients/{cid}/register/latest", headers={"Authorization": f"Bearer {bearer}"}
    )
    assert latest.status_code == 200, latest.text
    return latest.json(), _generated_audit(c, bearer)


def test_valid_other_axes_are_stored_in_the_approved_order(app_client) -> None:  # noqa: F811
    body, audit = _generate(
        app_client,
        lambda t, z: [
            _entry(t, axis="detection", other_axes=["response", "prevention"]),
            _entry(z, axis="prevention", other_axes=[]),
        ],
    )
    by_sid = {e["source_id"]: e for e in body["entries"]}
    assert len(by_sid) == 2
    t, z = sorted(by_sid, key=lambda s: by_sid[s]["axis"])
    assert by_sid[t]["other_axes"] == ["prevention", "response"]
    assert by_sid[z]["other_axes"] == []
    # Nothing dropped, said positively.
    assert audit["other_axes_dropped"] == {}


def test_an_invalid_a_duplicate_and_the_primary_repeated_are_dropped_and_counted(
    app_client,  # noqa: F811
) -> None:
    body, audit = _generate(
        app_client,
        lambda t, z: [
            _entry(
                t,
                axis="detection",
                other_axes=["Response", "prevention", "prevention", "detection", "severe"],
            ),
        ],
    )
    (entry,) = body["entries"]
    # What must appear first: what was kept, case-normalised like `axis`.
    assert entry["other_axes"] == ["prevention", "response"]
    assert audit["other_axes_dropped"] == {"duplicate": 1, "repeats_axis": 1, "invalid": 1}
    # The invalid token is named where every rejected token is named.
    assert audit["rejected_enum_values"]["other_axes"] == ["severe"]
    # #313: the axis breakdown counts the PRIMARY axis only.
    assert body["axis_counts"] == {"detection": 1, "prevention": 0, "response": 0}


def test_an_absent_or_non_list_value_is_not_recorded_and_counted(app_client) -> None:  # noqa: F811
    body, audit = _generate(
        app_client,
        lambda t, z: [
            _entry(t),  # no `other_axes` at all
            _entry(z, axis="prevention", other_axes="response"),
        ],
    )
    # NULL is "not recorded", never "none": the approved text asks for `[]`
    # when there are none, so an absent or unreadable value is not that claim.
    assert sorted((e["axis"], e["other_axes"]) for e in body["entries"]) == [
        ("detection", None),
        ("prevention", None),
    ]
    assert audit["other_axes_dropped"] == {"absent": 1, "not_a_list": 1}
