"""#854 review F3, Gene's option (c): regenerating keeps the consultant's ratings.

Before this, Regenerate minted a new version from the model alone, so every
rating a consultant had set was silently gone from the current register.

THE MATCH KEY is `source_id`: the finding an entry was drafted for (an ATT&CK
technique, a CSF subcategory or a ZT capability code). The prompt drafts one
entry per finding (G2), so a finding identifies its entry across versions.
`source` is not part of the key because it is derived from `source_id` (D5).
A rating is carried only when the key is UNAMBIGUOUS on both sides: exactly
one consultant-edited entry for that finding in the old version, and exactly
one entry for it in the new one. Anything else is not carried, and is listed.

Only CONSULTANT-edited ratings carry (`rating_edited_at` set); a model rating
is the model's, and the new run's model rating replaces it. A carried rating
replaces whatever the new run's model proposed, because the consultant's
judgement is what the edit path records.
"""

from __future__ import annotations

import pytest

from tests.unit.test_risk_register import (  # noqa: F401  (app_client is a fixture)
    _admin,
    _entries_payload,
    _entry,
    _generate,
    _seed_attack_and_zt,
    app_client,
)

pytestmark = pytest.mark.unit


def _unrated(title: str, source_id: str) -> str:
    return (
        '{"title": "' + title + '", "source_id": "' + source_id + '",'
        ' "likelihood": null, "impact": null}'
    )


def _world(app_client):  # noqa: F811
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, capability = _seed_attack_and_zt(c, bearer, cid)
    return c, provider, bearer, cid, technique, capability


def _patch(c, bearer, cid, entry_id, body):
    r = c.patch(
        f"/risk/clients/{cid}/register/entries/{entry_id}",
        headers={"Authorization": f"Bearer {bearer}"},
        json=body,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _by_sid(body: dict) -> dict:
    return {e["source_id"]: e for e in body["entries"]}


def test_a_consultant_rating_survives_regenerate(app_client) -> None:  # noqa: F811
    c, provider, bearer, cid, technique, _ = _world(app_client)
    v1 = _generate(c, provider, bearer, cid, _entries_payload(_unrated("A", technique)))
    _patch(c, bearer, cid, v1["entries"][0]["id"], {"likelihood": "high", "impact": "major"})

    v2 = _generate(c, provider, bearer, cid, _entries_payload(_unrated("A again", technique)))
    e = _by_sid(v2)[technique]
    # high x major: (3+1)*(3+1) = 16, High.
    assert (e["likelihood"], e["impact"], e["tier"]) == ("high", "major", "high")
    assert e["rating_edited_at"] is not None
    assert v2["ratings_carried_recorded"] is True
    assert v2["ratings_carried"] == 1
    assert v2["ratings_carried_from_version"] == 1
    assert v2["ratings_not_carried"] == []


def test_a_carried_rating_replaces_the_new_model_rating(app_client) -> None:  # noqa: F811
    c, provider, bearer, cid, technique, _ = _world(app_client)
    v1 = _generate(c, provider, bearer, cid, _entries_payload(_entry("A", source_id=technique)))
    _patch(c, bearer, cid, v1["entries"][0]["id"], {"likelihood": "low", "impact": "minor"})
    v2 = _generate(c, provider, bearer, cid, _entries_payload(_entry("A", source_id=technique)))
    e = _by_sid(v2)[technique]
    assert (e["likelihood"], e["impact"]) == ("low", "minor")


def test_a_model_rating_is_not_carried(app_client) -> None:  # noqa: F811
    c, provider, bearer, cid, technique, _ = _world(app_client)
    _generate(c, provider, bearer, cid, _entries_payload(_entry("A", source_id=technique)))
    v2 = _generate(c, provider, bearer, cid, _entries_payload(_unrated("A", technique)))
    e = _by_sid(v2)[technique]
    assert (e["likelihood"], e["impact"], e["rating_edited_at"]) == (None, None, None)
    assert v2["ratings_carried"] == 0
    assert v2["ratings_not_carried"] == []


def test_a_rating_with_no_matching_entry_is_listed_not_dropped(app_client) -> None:  # noqa: F811
    c, provider, bearer, cid, technique, capability = _world(app_client)
    v1 = _generate(c, provider, bearer, cid, _entries_payload(_unrated("A", technique)))
    _patch(c, bearer, cid, v1["entries"][0]["id"], {"likelihood": "low", "impact": "minor"})
    # The new run drafted nothing for that finding.
    v2 = _generate(c, provider, bearer, cid, _entries_payload(_unrated("Z", capability)))
    assert v2["ratings_carried"] == 0
    assert v2["ratings_not_carried"] == [technique]


def test_an_ambiguous_match_is_not_carried(app_client) -> None:  # noqa: F811
    """Two entries for one finding in the new version: carrying to either would
    be a guess, so neither gets it and the finding is listed."""
    c, provider, bearer, cid, technique, _ = _world(app_client)
    v1 = _generate(c, provider, bearer, cid, _entries_payload(_unrated("A", technique)))
    _patch(c, bearer, cid, v1["entries"][0]["id"], {"likelihood": "low", "impact": "minor"})
    v2 = _generate(
        c,
        provider,
        bearer,
        cid,
        _entries_payload(_unrated("A1", technique), _unrated("A2", technique)),
    )
    assert all(e["likelihood"] is None for e in v2["entries"])
    assert v2["ratings_carried"] == 0
    assert v2["ratings_not_carried"] == [technique]


def test_a_first_register_records_nothing_to_carry(app_client) -> None:  # noqa: F811
    c, provider, bearer, cid, technique, _ = _world(app_client)
    v1 = _generate(c, provider, bearer, cid, _entries_payload(_unrated("A", technique)))
    assert v1["ratings_carried_recorded"] is True
    assert v1["ratings_carried"] == 0
    assert v1["ratings_carried_from_version"] is None
    assert v1["ratings_not_carried"] == []
