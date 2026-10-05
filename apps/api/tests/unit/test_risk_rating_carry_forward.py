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
    _pdf_text,
    _seed_attack_and_zt,
    _session,
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
    # The new run proposed high x catastrophic (critical); the consultant's
    # low x minor replaces it, and the tier is derived from the carried pair:
    # (1+1)*(1+1) = 4, Low.
    assert (e["likelihood"], e["impact"], e["tier"]) == ("low", "minor", "low")


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
    assert v2["ratings_not_carried"] == [{"key": technique, "reason": "no_entry"}]


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
    assert v2["ratings_not_carried"] == [{"key": technique, "reason": "ambiguous"}]


def test_a_first_register_records_nothing_to_carry(app_client) -> None:  # noqa: F811
    c, provider, bearer, cid, technique, _ = _world(app_client)
    v1 = _generate(c, provider, bearer, cid, _entries_payload(_unrated("A", technique)))
    assert v1["ratings_carried_recorded"] is True
    assert v1["ratings_carried"] == 0
    assert v1["ratings_carried_from_version"] is None
    assert v1["ratings_not_carried"] == []


def test_two_old_entries_for_one_finding_carry_nothing(app_client) -> None:  # noqa: F811
    """#854 round 4 (blocking). The old version had TWO entries for one finding,
    one consultant-rated and one model-rated; the new one has one. Counting only
    edited entries called that unambiguous and put the consultant's rating on
    a risk they never rated. Every old entry counts, so it is not carried."""
    c, provider, bearer, cid, technique, _ = _world(app_client)
    v1 = _generate(
        c,
        provider,
        bearer,
        cid,
        _entries_payload(
            _unrated("Rated by consultant", technique), _entry("Model", source_id=technique)
        ),
    )
    rated = next(e for e in v1["entries"] if e["title"] == "Rated by consultant")
    _patch(c, bearer, cid, rated["id"], {"likelihood": "low", "impact": "minor"})
    v2 = _generate(c, provider, bearer, cid, _entries_payload(_unrated("One", technique)))
    [e] = v2["entries"]
    assert (e["likelihood"], e["rating_edited_at"]) == (None, None)
    assert v2["ratings_carried"] == 0
    assert v2["ratings_not_carried"] == [{"key": technique, "reason": "ambiguous"}]


def test_not_carried_counts_ratings_not_findings(app_client) -> None:  # noqa: F811
    """#854 round 4 (blocking). Two consultant ratings on two entries for ONE
    finding are two ratings lost, and the list says two, not one."""
    c, provider, bearer, cid, technique, _ = _world(app_client)
    v1 = _generate(
        c,
        provider,
        bearer,
        cid,
        _entries_payload(_unrated("A1", technique), _unrated("A2", technique)),
    )
    for e in v1["entries"]:
        _patch(c, bearer, cid, e["id"], {"likelihood": "low"})
    v2 = _generate(c, provider, bearer, cid, _entries_payload(_unrated("A", technique)))
    assert v2["ratings_not_carried"] == [
        {"key": technique, "reason": "ambiguous"},
        {"key": technique, "reason": "ambiguous"},
    ]


def test_an_entry_with_no_source_id_is_listed_by_title(app_client) -> None:  # noqa: F811
    c, provider, bearer, cid, technique, _ = _world(app_client)
    v1 = _generate(c, provider, bearer, cid, _entries_payload(_unrated("Orphan", "T0000")))
    [orphan] = v1["entries"]
    assert orphan["source_id"] is None  # T0000 names no finding, so it was dropped
    _patch(c, bearer, cid, orphan["id"], {"likelihood": "low", "impact": "minor"})
    v2 = _generate(c, provider, bearer, cid, _entries_payload(_unrated("A", technique)))
    assert v2["ratings_not_carried"] == [{"key": "Orphan", "reason": "no_source_id"}]


def test_who_rated_and_when_are_copied_verbatim(app_client) -> None:  # noqa: F811
    """The rating was admin A's; admin B regenerates. The carried entry still
    names A and A's time, not B and the regenerate."""
    import uuid

    from app.models.user import User, UserRole

    c, provider, bearer_a, cid, technique, _ = _world(app_client)
    v1 = _generate(c, provider, bearer_a, cid, _entries_payload(_unrated("A", technique)))
    rated = _patch(
        c, bearer_a, cid, v1["entries"][0]["id"], {"likelihood": "low", "impact": "minor"}
    )
    [before] = rated["entries"]

    b = c.post(
        "/auth/register",
        json={
            "email": "second@kentro-b.example",
            "password": "correct horse battery staple!",
            "display_name": "B",
        },
    )
    assert b.status_code == 201, b.text
    with _session() as s:
        user = s.get(User, uuid.UUID(b.json()["user"]["id"]))
        user.role = UserRole.ADMIN
        user.client_id = None
        s.commit()
    login = c.post(
        "/auth/login",
        json={"email": "second@kentro-b.example", "password": "correct horse battery staple!"},
    )
    assert login.status_code == 200, login.text
    bearer_b = login.json()["access_token"]
    assert b.json()["user"]["id"] != before["rating_edited_by"]

    v2 = _generate(c, provider, bearer_b, cid, _entries_payload(_unrated("A", technique)))
    [after] = v2["entries"]
    assert after["rating_edited_by"] == before["rating_edited_by"]
    assert after["rating_edited_at"] == before["rating_edited_at"]


def test_a_fully_cleared_rating_carries_as_unrated_with_no_credit(app_client) -> None:  # noqa: F811
    c, provider, bearer, cid, technique, _ = _world(app_client)
    v1 = _generate(c, provider, bearer, cid, _entries_payload(_entry("A", source_id=technique)))
    _patch(c, bearer, cid, v1["entries"][0]["id"], {"likelihood": None, "impact": None})
    # The new run rates it; the consultant's deliberate clear replaces that.
    v2 = _generate(c, provider, bearer, cid, _entries_payload(_entry("A", source_id=technique)))
    [e] = v2["entries"]
    assert (e["likelihood"], e["impact"], e["tier"]) == (None, None, None)
    assert v2["ratings_carried"] == 1
    bh = {"Authorization": f"Bearer {bearer}"}
    ex = c.post(f"/risk/clients/{cid}/register/export", headers=bh).json()
    pdf = c.get(f"/artifacts/{ex['pdf_artifact_id']}/download", headers={**bh, "X-Client-Id": cid})
    text = " ".join(_pdf_text(pdf.content).split())
    assert "Ratings set by a consultant" not in text


def test_a_carried_rating_reaches_the_export(app_client) -> None:  # noqa: F811
    import io

    from openpyxl import load_workbook

    c, provider, bearer, cid, technique, _ = _world(app_client)
    v1 = _generate(c, provider, bearer, cid, _entries_payload(_unrated("A", technique)))
    _patch(c, bearer, cid, v1["entries"][0]["id"], {"likelihood": "low", "impact": "minor"})
    _generate(c, provider, bearer, cid, _entries_payload(_unrated("A", technique)))
    bh = {"Authorization": f"Bearer {bearer}"}
    ex = c.post(f"/risk/clients/{cid}/register/export", headers=bh).json()
    raw = c.get(
        f"/artifacts/{ex['xlsx_artifact_id']}/download", headers={**bh, "X-Client-Id": cid}
    ).content
    wb = load_workbook(io.BytesIO(raw))
    rows = list(wb["Risk Register"].iter_rows(values_only=True))
    row = dict(zip(rows[0], rows[1], strict=True))
    assert (row["Likelihood"], row["Impact"], row["Tier"]) == ("Low", "Minor", "Low")
    assert row["Origin"] == "ai_generated; rating edited by consultant"
    summary = [str(r[0]) for r in wb["Summary"].iter_rows(values_only=True) if r and r[0]]
    assert any(line.startswith("Ratings set by a consultant: 1 of 1 ") for line in summary)


def test_the_audit_untiered_count_describes_the_stored_register(app_client) -> None:  # noqa: F811
    """#854 round 4. The model left the new entry unrated and the carry rated
    it: the audit row says 0 untiered, as the stored register does."""
    from tests.unit.test_risk_register import _generated_audit

    c, provider, bearer, cid, technique, _ = _world(app_client)
    v1 = _generate(c, provider, bearer, cid, _entries_payload(_unrated("A", technique)))
    _patch(c, bearer, cid, v1["entries"][0]["id"], {"likelihood": "low", "impact": "minor"})
    v2 = _generate(c, provider, bearer, cid, _entries_payload(_unrated("A", technique)))
    assert v2["entries_without_tier"] == 0
    assert _generated_audit(c, bearer)["entries_without_tier"] == 0
