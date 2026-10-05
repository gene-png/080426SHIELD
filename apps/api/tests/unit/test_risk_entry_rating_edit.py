"""#844: a consultant can set or clear an entry's likelihood and impact.

Before this, an entry the model left unrated had no tier and no way to get one:
the risk router had gate, generate, export and latest, and the consultant banner
told them to regenerate, which spends another model call and can come back
unrated again. The approved prompt (#806, G3 option c) returns JSON null where
the evidence cannot support a rating, so unrated entries are now EXPECTED, and
the consultant is who rates them.

Every test goes through the endpoints a consultant's screen calls: the PATCH,
then `latest`, then `export`. The unrated starting state is built by the model
omitting the key (the prompt's own null), never by writing a row directly.
"""

from __future__ import annotations

import pytest

from tests.unit.test_risk_register import (  # noqa: F401  (app_client is a fixture)
    _admin,
    _entries_payload,
    _entry,
    _generate,
    _seed_attack_and_zt,
    _session,
    app_client,
)

pytestmark = pytest.mark.unit


def _unrated(title: str) -> str:
    """An entry whose likelihood and impact the model returned as JSON null."""
    return (
        '{"title": "' + title + '", "axis": "detection", "likelihood": null,'
        ' "impact": null, "recommended_action": "remediate"}'
    )


def _setup(app_client, *entries: str) -> tuple:  # noqa: F811
    c, provider = app_client
    bearer, cid = _admin(c)
    _seed_attack_and_zt(c, bearer, cid)
    body = _generate(c, provider, bearer, cid, _entries_payload(*entries))
    return c, provider, bearer, cid, body


def _patch(c, bearer: str, cid: str, entry_id: str, body: dict):
    return c.patch(
        f"/risk/clients/{cid}/register/entries/{entry_id}",
        headers={"Authorization": f"Bearer {bearer}"},
        json=body,
    )


def _latest(c, bearer: str, cid: str) -> dict:
    r = c.get(
        f"/risk/clients/{cid}/register/latest",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_a_consultant_rating_gives_an_unrated_entry_a_code_derived_tier(
    app_client,  # noqa: F811
) -> None:
    c, _, bearer, cid, body = _setup(app_client, _unrated("Unrated one"))
    entry = body["entries"][0]
    assert entry["tier"] is None
    assert body["entries_without_tier"] == 1

    r = _patch(c, bearer, cid, entry["id"], {"likelihood": "high", "impact": "catastrophic"})
    assert r.status_code == 200, r.text

    # Read back through `latest`, so the assertion is on what was STORED.
    after = _latest(c, bearer, cid)
    [e] = after["entries"]
    assert (e["likelihood"], e["impact"]) == ("high", "catastrophic")
    # The NIST 800-30 rule in `engine.tier_for`: High x Catastrophic is Critical.
    assert e["tier"] == "critical"
    assert after["entries_without_tier"] == 0
    assert after["tier_counts"]["critical"] == 1
    assert e["rating_edited_at"] is not None
    assert e["rating_edited_by"] is not None


def test_a_model_rating_is_not_marked_as_consultant_set(app_client) -> None:  # noqa: F811
    """The marker is what keeps the Origin column honest, so it must be absent
    until someone edits. Without this, a marker set on every row would pass the
    test above."""
    _, _, _, _, body = _setup(app_client, _entry("Rated by the model"))
    [e] = body["entries"]
    assert e["tier"] == "critical"
    assert e["rating_edited_at"] is None
    assert e["rating_edited_by"] is None


def test_setting_one_half_leaves_the_entry_unrated_and_untiered(app_client) -> None:  # noqa: F811
    c, _, bearer, cid, body = _setup(app_client, _unrated("Half"))
    r = _patch(c, bearer, cid, body["entries"][0]["id"], {"likelihood": "medium"})
    assert r.status_code == 200, r.text
    [e] = _latest(c, bearer, cid)["entries"]
    assert e["likelihood"] == "medium"
    assert e["impact"] is None
    assert e["tier"] is None


def test_null_clears_a_rating_back_to_unrated(app_client) -> None:  # noqa: F811
    c, _, bearer, cid, body = _setup(app_client, _entry("Was rated"))
    r = _patch(c, bearer, cid, body["entries"][0]["id"], {"impact": None})
    assert r.status_code == 200, r.text
    after = _latest(c, bearer, cid)
    [e] = after["entries"]
    assert e["likelihood"] == "high"
    assert e["impact"] is None
    assert e["tier"] is None
    assert after["entries_without_tier"] == 1


def test_an_omitted_field_is_left_alone_rather_than_cleared(app_client) -> None:  # noqa: F811
    """Absent is not null. A body naming only `impact` must not wipe likelihood."""
    c, _, bearer, cid, body = _setup(app_client, _entry("Keep likelihood"))
    r = _patch(c, bearer, cid, body["entries"][0]["id"], {"impact": "minor"})
    assert r.status_code == 200, r.text
    [e] = _latest(c, bearer, cid)["entries"]
    assert e["likelihood"] == "high"
    assert e["impact"] == "minor"
    # High x Minor: score (3+1)*(1+1) = 8, which is Low (>= 4, < 9).
    assert e["tier"] == "low"


def test_the_edit_is_audited_with_before_and_after(app_client) -> None:  # noqa: F811
    from sqlalchemy import select

    from app.models.audit_entry import AuditEntry

    c, _, bearer, cid, body = _setup(app_client, _unrated("Audited"))
    entry_id = body["entries"][0]["id"]
    r = _patch(c, bearer, cid, entry_id, {"likelihood": "low", "impact": "moderate"})
    assert r.status_code == 200, r.text
    with _session() as s:
        rows = (
            s.execute(select(AuditEntry).where(AuditEntry.action == "risk_entry.rating_edited"))
            .scalars()
            .all()
        )
    assert len(rows) == 1
    details = rows[0].details
    assert details["before"] == {"likelihood": None, "impact": None, "tier": None}
    # Low x Moderate: (1+1)*(2+1) = 6, Low.
    assert details["after"] == {"likelihood": "low", "impact": "moderate", "tier": "low"}


@pytest.mark.parametrize(
    "body",
    [
        {"likelihood": "severe"},
        {"impact": "High"},
        {"likelihood": "medium", "tier": "critical"},
        {},
    ],
    ids=["unknown-likelihood", "wrong-case-impact", "tier-in-body", "empty-body"],
)
def test_a_body_the_engine_cannot_use_is_refused_and_changes_nothing(
    app_client, body  # noqa: F811
) -> None:
    """The tier is never accepted from a caller (core principle 1), a token must
    be the engine's exact spelling (this is a typed control, not model output),
    and an empty body is a request that changes nothing."""
    c, _, bearer, cid, gen = _setup(app_client, _unrated("Untouched"))
    r = _patch(c, bearer, cid, gen["entries"][0]["id"], body)
    assert r.status_code == 422, r.text
    [e] = _latest(c, bearer, cid)["entries"]
    assert (e["likelihood"], e["impact"], e["tier"]) == (None, None, None)
    assert e["rating_edited_at"] is None


def test_an_entry_under_another_client_is_not_found(app_client) -> None:  # noqa: F811
    c, _, bearer, cid, body = _setup(app_client, _unrated("Mine"))
    other = c.post(
        "/admin/clients",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"legal_name": "Other"},
    ).json()["id"]
    r = _patch(c, bearer, other, body["entries"][0]["id"], {"likelihood": "low"})
    assert r.status_code == 404, r.text
    assert r.json()["error"]["reason"] == "risk_entry_not_found"
    [e] = _latest(c, bearer, cid)["entries"]
    assert e["likelihood"] is None


def test_an_entry_on_a_superseded_register_is_refused(app_client) -> None:  # noqa: F811
    c, provider, bearer, cid, first = _setup(app_client, _unrated("Old version"))
    _generate(c, provider, bearer, cid, _entries_payload(_unrated("New version")))
    r = _patch(c, bearer, cid, first["entries"][0]["id"], {"likelihood": "low"})
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "risk_register_superseded"


def test_an_entry_on_a_published_register_is_refused(app_client) -> None:  # noqa: F811
    """Until #737 separates them, export IS publication: it sets `finalized_at`,
    which is what the client dashboard reads. A rating changed after that would
    change numbers a client is already reading, with nothing re-published."""
    c, _, bearer, cid, body = _setup(app_client, _unrated("Published"))
    ex = c.post(
        f"/risk/clients/{cid}/register/export",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert ex.status_code == 200, ex.text
    r = _patch(c, bearer, cid, body["entries"][0]["id"], {"likelihood": "low"})
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "risk_register_published"
    [e] = _latest(c, bearer, cid)["entries"]
    assert e["likelihood"] is None


def test_a_client_user_cannot_edit(app_client) -> None:  # noqa: F811
    c, _, bearer, cid, body = _setup(app_client, _unrated("Admin only"))
    r = c.patch(
        f"/risk/clients/{cid}/register/entries/{body['entries'][0]['id']}",
        json={"likelihood": "low"},
    )
    assert r.status_code == 401, r.text


def test_a_client_role_user_is_forbidden(app_client) -> None:  # noqa: F811
    c, _, bearer, cid, body = _setup(app_client, _unrated("Admin only"))
    c.post(
        f"/admin/clients/{cid}/domains",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"domain": "acme.example"},
    )
    user = c.post(
        "/auth/register",
        json={
            "email": "user@acme.example",
            "password": "correct horse battery staple!",
            "display_name": "U",
        },
    )
    cbearer = user.json()["tokens"]["access_token"]
    r = _patch(c, cbearer, cid, body["entries"][0]["id"], {"likelihood": "low"})
    assert r.status_code == 403, r.text
    [e] = _latest(c, bearer, cid)["entries"]
    assert e["likelihood"] is None


def _interleave(app_client, change, *, other_client: bool = False) -> tuple:  # noqa: F811
    """Run one PATCH with `change(session, entry_id)` applied by ANOTHER session
    after the PATCH read the row and before its write -- the interleaving two
    concurrent requests produce. Returns `(response, entry_id, c, bearer, cid)`.
    """
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    c, provider, bearer, cid, body = _setup(app_client, _entry("Raced"))
    entry_id = body["entries"][0]["id"]
    if other_client:
        # A SECOND client with an OPEN register. An EXISTS subquery that is not
        # correlated on `risk_entries.register_id` would find this row and let
        # the write through; correlated, it looks only at the raced register.
        other = c.post(
            "/admin/clients",
            headers={"Authorization": f"Bearer {bearer}"},
            json={"legal_name": "Other"},
        ).json()["id"]
        _seed_attack_and_zt(c, bearer, other)
        _generate(c, provider, bearer, other, _entries_payload(_entry("Other open")))
    fired: list[bool] = []

    def _before_write(state) -> None:
        if state.is_update and not fired:
            fired.append(True)
            with _session() as other:
                change(other, entry_id)
                other.commit()

    event.listen(Session, "do_orm_execute", _before_write)
    try:
        r = _patch(c, bearer, cid, entry_id, {"likelihood": "low"})
    finally:
        event.remove(Session, "do_orm_execute", _before_write)
    assert fired, "the interleaving never ran, so this test proves nothing"
    return r, entry_id, c, bearer, cid


def test_an_entry_changed_underneath_the_edit_is_refused_and_kept(app_client) -> None:  # noqa: F811
    """#854 review, F7. Another edit changed the IMPACT between this PATCH's
    read and its write. A plain write would store likelihood low with the
    other's impact under a tier derived from the pair this PATCH read; the
    compare-and-swap writes nothing, names the cause, and the other edit
    stands."""
    import uuid

    from app.models.risk_register import RiskEntry

    def _other_edit(s, entry_id):
        e = s.get(RiskEntry, uuid.UUID(entry_id))
        e.impact, e.tier = "minor", "low"  # high x minor: (3+1)*(1+1)=8, Low

    r, entry_id, c, bearer, cid = _interleave(app_client, _other_edit)
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "risk_entry_changed"
    assert r.json()["error"]["message"] == (
        "This entry changed while you were editing it. Reload the page and try again."
    )
    [e] = _latest(c, bearer, cid)["entries"]
    assert (e["likelihood"], e["impact"], e["tier"]) == ("high", "minor", "low")
    assert e["rating_edited_at"] is None


def test_a_register_published_underneath_the_edit_is_refused(app_client) -> None:  # noqa: F811
    """The register was published between the PATCH's checks and its write.
    The compare-and-swap re-checks the register in the same statement, so the
    published numbers do not change.

    NOT the whole PATCH-versus-export race: an export that is still RENDERING
    has not set `finalized_at` yet, so this re-check passes during it. That
    half is held by the register lock (see the two lock tests below), which
    SQLite does not enforce."""
    import uuid
    from datetime import UTC, datetime

    from app.models.risk_register import RiskEntry, RiskRegister

    def _publish(s, entry_id):
        e = s.get(RiskEntry, uuid.UUID(entry_id))
        s.get(RiskRegister, e.register_id).finalized_at = datetime.now(UTC)

    r, entry_id, c, bearer, cid = _interleave(app_client, _publish, other_client=True)
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "risk_register_published"
    [e] = _latest(c, bearer, cid)["entries"]
    assert (e["likelihood"], e["impact"], e["tier"]) == ("high", "catastrophic", "critical")


def _statements(request) -> list[tuple[str, str, str]]:
    """Run `request()` and return, IN ORDER, every ORM SELECT and UPDATE the
    endpoint issued as `(kind, table, lock)`, lock being "update", "share" or
    "none". ORDER is the point: a lock taken after the reads it protects is the
    race it exists to close. SQLite ignores row locks, so this pins the
    statements and their order; the serialisation itself is Postgres's and is
    not exercised here."""
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    seen: list[tuple[str, str, str]] = []

    def _spy(state) -> None:
        stmt = state.statement
        if state.is_select:
            arg = getattr(stmt, "_for_update_arg", None)
            lock = "none" if arg is None else ("share" if arg.read else "update")
            for t in stmt.get_final_froms():
                seen.append(("select", getattr(t, "name", str(t)), lock))
        elif state.is_update:
            seen.append(("update", stmt.table.name, "none"))

    event.listen(Session, "do_orm_execute", _spy)
    try:
        r = request()
    finally:
        event.remove(Session, "do_orm_execute", _spy)
    assert r.status_code == 200, r.text
    return seen


def _first(seen: list, pred) -> int:
    for i, s in enumerate(seen):
        if pred(s):
            return i
    raise AssertionError(f"no matching statement in {seen}")


def test_export_locks_the_register_before_reading_entries(app_client) -> None:  # noqa: F811
    """#854 review rounds 2 and 3. Export read the entries, rendered for
    seconds and only then set `finalized_at`, so an edit committed in that gap
    reached the dashboard and not the delivered file. Export takes the register
    FOR UPDATE, and it must do so BEFORE its first read of the entries -- a
    lock taken late is the race again. The race itself is NOT exercised here
    (SQLite has no row locks); the order of the statements is."""
    c, _, bearer, cid, _ = _setup(app_client, _entry("Exported"))
    seen = _statements(
        lambda: c.post(
            f"/risk/clients/{cid}/register/export",
            headers={"Authorization": f"Bearer {bearer}"},
        )
    )
    locked = _first(seen, lambda s: s == ("select", "risk_registers", "update"))
    entries = _first(seen, lambda s: s[0] == "select" and s[1] == "risk_entries")
    assert locked < entries, seen


def test_the_edit_takes_the_register_for_share_before_reading_or_writing(
    app_client,  # noqa: F811
) -> None:
    """The edit's FOR SHARE must be its FIRST read of the register (the checks
    read that row) and must come before the compare-and-swap UPDATE."""
    c, _, bearer, cid, body = _setup(app_client, _unrated("Shared"))
    seen = _statements(
        lambda: _patch(c, bearer, cid, body["entries"][0]["id"], {"likelihood": "low"})
    )
    first_register = _first(seen, lambda s: s[0] == "select" and s[1] == "risk_registers")
    assert seen[first_register] == ("select", "risk_registers", "share"), seen
    cas = _first(seen, lambda s: s == ("update", "risk_entries", "none"))
    assert first_register < cas, seen


def test_export_refuses_a_register_superseded_while_it_waited(app_client) -> None:  # noqa: F811
    """#854 review round 3. A generate that commits while export waits for the
    register lock supersedes the row export already looked up. Re-checked under
    the lock, so export refuses rather than finalizing a version the consultant
    is no longer looking at. The interleaving is real: another session commits
    the supersession just before export's locking SELECT runs."""
    import uuid

    from sqlalchemy import event
    from sqlalchemy.orm import Session

    from app.models.risk_register import RiskRegister

    c, _, bearer, cid, body = _setup(app_client, _entry("Old"))
    reg_id = uuid.UUID(body["id"])
    fired: list[bool] = []

    def _supersede_first(state) -> None:
        arg = getattr(state.statement, "_for_update_arg", None)
        if state.is_select and arg is not None and not fired:
            fired.append(True)
            with _session() as other:
                old = other.get(RiskRegister, reg_id)
                newer = RiskRegister(
                    client_id=old.client_id, version=old.version + 1, provenance={}
                )
                other.add(newer)
                other.flush()
                old.superseded_by = newer.id
                other.commit()

    event.listen(Session, "do_orm_execute", _supersede_first)
    try:
        r = c.post(
            f"/risk/clients/{cid}/register/export",
            headers={"Authorization": f"Bearer {bearer}"},
        )
    finally:
        event.remove(Session, "do_orm_execute", _supersede_first)
    assert fired, "the interleaving never ran, so this test proves nothing"
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "risk_register_superseded"
    assert r.json()["error"]["message"] == (
        "A newer version of the Risk Register was generated while this export was "
        "starting. Reload the page and export the current version."
    )
    with _session() as s:
        assert s.get(RiskRegister, reg_id).finalized_at is None


def test_a_half_set_rating_is_marked_as_edited_by_the_consultant(app_client) -> None:  # noqa: F811
    """Gene's ruling (a) (#736, 5986057990 item 10). A consultant sets only the
    likelihood on an unrated entry: the row is still unrated, AND the half they
    set is theirs, so the XLSX Origin reads "rating edited by consultant" and
    the summary counts it. Before the ruling this was pinned the other way."""
    import io

    from openpyxl import load_workbook

    c, _, bearer, cid, body = _setup(app_client, _unrated("Half"))
    r = _patch(c, bearer, cid, body["entries"][0]["id"], {"likelihood": "medium"})
    assert r.status_code == 200, r.text
    bh = {"Authorization": f"Bearer {bearer}"}
    ex = c.post(f"/risk/clients/{cid}/register/export", headers=bh).json()
    raw = c.get(
        f"/artifacts/{ex['xlsx_artifact_id']}/download", headers={**bh, "X-Client-Id": cid}
    ).content
    wb = load_workbook(io.BytesIO(raw))
    rows = list(wb["Risk Register"].iter_rows(values_only=True))
    row = dict(zip(rows[0], rows[1], strict=True))
    assert (row["Likelihood"], row["Impact"], row["Tier"]) == ("Medium", "Not rated", "Not rated")
    assert row["Origin"] == "ai_generated; rating edited by consultant"
    summary = [str(r[0]) for r in wb["Summary"].iter_rows(values_only=True) if r and r[0]]
    # The noun's agreement at 1 is a filed advisory, not pinned here.
    assert any(line.startswith("Ratings set by a consultant: 1 of 1 ") for line in summary)
