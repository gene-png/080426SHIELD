"""#474 E, review 6105054562 finding 2; ruling #736 6105137014, option (i).

A partly dropped `other_axes` list used to render as complete, the drop
reasons reaching only the generate audit row. Each entry now records its own
element drops in `other_axes_dropped` (migration 0066): NULL is "not recorded"
(pre-0066, or no readable list), `{}` is "none dropped". The CONSULTANT's Risk
screen states the unreadable ones, in the approved copy:

    "{n} AI-suggested axis could not be read and was dropped."
    "{n} AI-suggested axes could not be read and were dropped."

The client's dashboard and the client files carry no note: the kept axes are
accurate as far as they go, and a parse failure is not a client fact. So the
client dashboard response does not carry the field.

Driven through generate with a hand-built model response (fixture mode cannot
produce a drop) and read back through the API each reader reaches.
"""

from __future__ import annotations

import json

import pytest

from app.ai.llm import LLMResponse

from .test_risk_baseline_disclosure import _client_dashboard
from .test_risk_other_axes import _entry
from .test_risk_per_service import _export_texts
from .test_risk_register import (
    _admin,
    _seed_attack_and_zt,
    app_client,  # noqa: F401  -- the fixture, used by name below.
)

pytestmark = pytest.mark.unit


def _generate(app_client, entries_for):  # noqa: F811
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
    return c, bearer, cid, {e["source_id"]: e for e in latest.json()["entries"]}


def test_each_entry_records_its_own_element_drops(app_client) -> None:  # noqa: F811
    c, bearer, cid, by_sid = _generate(
        app_client,
        lambda t, z: [
            # One unreadable token, plus a duplicate and the primary repeated.
            _entry(
                t,
                axis="detection",
                other_axes=["prevention", "severe", "prevention", "detection"],
            ),
            # Two unreadable tokens.
            _entry(z, axis="prevention", other_axes=["response", "bogus", 7]),
        ],
    )
    t, z = sorted(by_sid, key=lambda s: by_sid[s]["axis"])
    # Positive first: what was kept, then what each entry records it dropped.
    assert by_sid[t]["other_axes"] == ["prevention"]
    assert by_sid[t]["other_axes_dropped"] == {"invalid": 1, "duplicate": 1, "repeats_axis": 1}
    assert by_sid[z]["other_axes"] == ["response"]
    assert by_sid[z]["other_axes_dropped"] == {"invalid": 2}


def test_a_clean_list_records_none_dropped_and_no_list_records_nothing(
    app_client,  # noqa: F811
) -> None:
    _c, _b, _cid, by_sid = _generate(
        app_client,
        lambda t, z: [
            _entry(t, axis="detection", other_axes=["response"]),
            _entry(z, axis="prevention"),  # no `other_axes`: not recorded
        ],
    )
    t, z = sorted(by_sid, key=lambda s: by_sid[s]["axis"])
    assert by_sid[t]["other_axes"] == ["response"]
    assert by_sid[t]["other_axes_dropped"] == {}
    assert by_sid[z]["other_axes"] is None
    assert by_sid[z]["other_axes_dropped"] is None


def test_the_client_dashboard_and_files_carry_no_drop_note(app_client) -> None:  # noqa: F811
    c, bearer, cid, by_sid = _generate(
        app_client,
        lambda t, z: [
            _entry(t, axis="detection", other_axes=["prevention", "severe"]),
            _entry(z, axis="prevention", other_axes=["bogus", "junk"]),
        ],
    )
    # Positive first: the consultant's register records the drops.
    assert sorted(e["other_axes_dropped"]["invalid"] for e in by_sid.values()) == [1, 2]
    texts = _export_texts(c, bearer, cid)
    for fmt in ("pdf", "docx", "xlsx"):
        flat = " ".join(texts[fmt].split())
        assert "Prevention" in flat, fmt  # the kept axis is printed
        assert "could not be read" not in flat, fmt
        assert "AI-suggested ax" not in flat, fmt
    dash = _client_dashboard(c, bearer, cid)
    assert dash["entries"], dash
    for e in dash["entries"]:
        assert "other_axes" in e, e
        assert "other_axes_dropped" not in e, e
    assert "could not be read" not in json.dumps(dash)


def _raw_nulls(cid: str) -> list[tuple[int, int]]:
    """`(other_axes IS NULL, other_axes_dropped IS NULL)` per entry, read with
    raw SQL: the ORM decodes JSON `'null'` and SQL NULL to the same None."""
    import sqlalchemy as sa

    from .test_risk_register import _session

    with _session() as s:
        return [
            (int(a), int(d))
            for a, d in s.execute(
                sa.text(
                    "SELECT other_axes IS NULL, other_axes_dropped IS NULL FROM risk_entries "
                    "WHERE client_id = :cid"
                ),
                {"cid": cid.replace("-", "")},
            ).all()
        ]


def _downgrade_to_0065() -> None:
    import os

    from alembic import command

    from .test_migration_0066_risk_other_axes import _cfg

    command.downgrade(_cfg(os.environ["DATABASE_URL"]), "0065")


def test_not_recorded_is_sql_null_so_the_downgrade_is_not_blocked(
    app_client,  # noqa: F811
) -> None:
    """Review of 655184cc, F3: "not recorded" written by GENERATE is SQL NULL,
    not the JSON text 'null', so 0066's downgrade (which refuses while a row
    records anything) is not blocked by rows that record nothing."""
    import sqlalchemy as sa

    from .test_risk_register import _session

    _c, _b, cid, by_sid = _generate(
        app_client,
        lambda t, z: [
            _entry(t, axis="detection"),  # no `other_axes`
            _entry(z, axis="prevention", other_axes="response"),  # not a list
        ],
    )
    # Positive first: both entries exist and read as "not recorded".
    assert [e["other_axes"] for e in by_sid.values()] == [None, None]
    assert _raw_nulls(cid) == [(1, 1), (1, 1)]
    _downgrade_to_0065()
    with _session() as s:
        cols = {r[1] for r in s.execute(sa.text("PRAGMA table_info(risk_entries)")).all()}
    assert "title" in cols
    assert not {"other_axes", "other_axes_dropped"} & cols, cols


def test_a_recorded_list_from_generate_blocks_the_downgrade(app_client) -> None:  # noqa: F811
    _c, _b, cid, by_sid = _generate(
        app_client,
        lambda t, z: [
            _entry(t, axis="detection", other_axes=["response"]),
            _entry(z, axis="prevention"),  # no `other_axes`
        ],
    )
    assert sorted(_raw_nulls(cid)) == [(0, 0), (1, 1)]
    with pytest.raises(
        RuntimeError, match="Refusing to downgrade 0066: 1 Risk Register entry records"
    ):
        _downgrade_to_0065()
