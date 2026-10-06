"""#177: whether a capability list's extraction attributed every item to an
uploaded row is PERSISTED (`attribution_complete`, migration 0058).

Before it, an empty `excluded_rows` was the stored form of both "nothing was
excluded" and "attribution failed", so the clean run -- the common case --
could only ever be reported as `unknown`. NULL still means "not recorded": a
list written before 0058, which is never read as complete by default.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.ai.llm import LLMResponse
from app.models.capability import CapabilityList
from tests._ai_runs import tech_debt_extract
from tests.unit.test_tech_debt_routes import (  # noqa: F401  (fixture)
    _register,
    _upload_csv,
    app_client,
)

pytestmark = pytest.mark.unit

CSV = b"Product,Vendor\nWiz,Wiz\nSplunk,Splunk\nLacework,Lacework\n"


def _item(name: str, row: int | None) -> dict:
    return {"name": name, "category": "SIEM", "annual_cost_usd": 1000, "source_row_index": row}


def _extract(c, provider, items: list[dict]) -> dict:
    provider.register(
        "extract.capabilities",
        lambda _p: LLMResponse(json.dumps({"items": items})),
    )
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    svc_id = c.post("/tech-debt/services", headers=h, json={"title": "TD"}).json()["id"]
    artifact_id = _upload_csv(c, bearer, "inv.csv", CSV)
    return tech_debt_extract(c, svc_id, h, artifact_id)


def _stored_flag(Sess, list_id: str):
    import uuid

    with Sess() as s:
        return s.execute(
            select(CapabilityList.attribution_complete).where(
                CapabilityList.id == uuid.UUID(list_id)
            )
        ).scalar_one()


def test_a_clean_extraction_records_its_attribution_as_complete(app_client) -> None:  # noqa: F811
    c, Sess, provider = app_client
    body = _extract(c, provider, [_item("Wiz", 0), _item("Splunk", 1)])
    assert _stored_flag(Sess, body["id"]) is True
    assert body["attribution_complete"] is True


def test_two_items_from_one_row_record_the_attribution_as_incomplete(
    app_client,  # noqa: F811
) -> None:
    """#193's case: three rows in, three items out, two of them claiming row 0.
    The arithmetic says nothing was excluded; a row was."""
    c, Sess, provider = app_client
    body = _extract(c, provider, [_item("Wiz", 0), _item("Wiz CNAPP", 0), _item("Splunk", 1)])
    assert _stored_flag(Sess, body["id"]) is False
    assert body["attribution_complete"] is False


def test_an_unattributed_item_records_the_attribution_as_incomplete(
    app_client,  # noqa: F811
) -> None:
    c, Sess, provider = app_client
    body = _extract(c, provider, [_item("Wiz", 0), _item("Splunk", None)])
    assert _stored_flag(Sess, body["id"]) is False


def test_the_migration_adds_a_nullable_column_and_removes_it_exactly(tmp_path) -> None:
    import os
    from pathlib import Path

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    url = f"sqlite:///{tmp_path / 'm.db'}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)

    def columns() -> dict:
        eng = create_engine(url)
        try:
            return {c["name"]: c for c in inspect(eng).get_columns("capability_lists")}
        finally:
            eng.dispose()

    command.upgrade(cfg, "0058")
    col = columns()["attribution_complete"]
    assert col["nullable"] is True
    assert col["default"] is None
    command.downgrade(cfg, "0057")
    assert "attribution_complete" not in columns()
    command.upgrade(cfg, "head")
    assert "attribution_complete" in columns()
