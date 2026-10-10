"""#984: catalog text reaches the model as the catalog has it, whatever the
client is called, and the client's own data is still redacted.

Strict redaction rewrote every string in an AI payload, so a client whose legal
name is a word in a catalog had that catalog text rewritten before the model
read it: "Critical" turned GV.OC-04's outcome into "[CLIENT] objectives, ...",
and `llm_calls.redacted_counts.client_org` counted the hit as a client-name
removal. The fix (the advisor's option (a) on #736) exempts a REGISTERED
catalog-sourced payload field from redaction, and guards it: the field is
rebuilt from the catalog before and after redaction and must match byte for
byte, or the call fails loudly before anything egresses.

Each test goes through `LLMClient.invoke`, the one egress path, and reads what
the provider received. Expected catalog text comes from the catalog's public
accessors; the client name in each test is a word chosen because it collides,
and each test first proves the collision is real (plain `redact_payload` does
rewrite the text), so it cannot pass vacuously.

ATT&CK's `technique_details` is on main and is tested through its run and
`/ai/preview` in `test_attack_technique_details_redaction.py`. CSF's
`subcategory_definitions` is registered here and built by the #806 CSF prompt
PR; ZT's `capability_details` is built and registered by #981, and the ZT test
below goes through that registration.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.catalog_fields import (
    CatalogFieldMismatch,
    redact_ai_payload,
    register_catalog_field,
)
from app.ai.llm import FixtureProvider, LLMClient, LLMResponse
from app.ai.redact import redact_payload
from app.models.llm_call import LLMCall

pytestmark = pytest.mark.unit


@pytest.fixture()
def db_session(tmp_path) -> Iterator[Session]:
    url = f"sqlite:///{tmp_path / 'shield-catalog-fields.db'}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    db = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()
    try:
        yield db
    finally:
        db.close()


def _invoke(db: Session, payload: dict[str, Any], org: str) -> tuple[list[dict], LLMCall]:
    """One strict-mode call; returns what the provider received and the row."""
    sent: list[dict] = []
    provider = FixtureProvider()

    def _record(p: dict) -> LLMResponse:
        sent.append({k: v for k, v in p.items() if not k.startswith("__")})
        return LLMResponse("{}")

    provider.register("catalog_probe", _record)
    LLMClient(provider).invoke(
        db,
        purpose="catalog_probe",
        prompt="p",
        payload=payload,
        requested_by=uuid.uuid4(),
        redaction_mode="strict",
        client_org_name=org,
    )
    row = db.execute(select(LLMCall)).scalars().one()
    return sent, row


def _collides(field: str, value: Any, org: str) -> bool:
    out, _ = redact_payload({field: value}, mode="strict", client_org_name=org)
    return out[field] != value


# --- CSF: `subcategory_definitions`, org "Critical" --------------------------


def _csf_definitions_naming(word: str) -> dict[str, str]:
    from app.csf.catalog import SUBCATEGORIES

    return {s.code: s.outcome for s in SUBCATEGORIES if word in s.outcome.split()}


def test_csf_definitions_reach_the_model_unchanged_for_a_client_named_critical(
    db_session,
) -> None:
    import app.routes.csf  # noqa: F401  (registers the field, as the app does)

    definitions = _csf_definitions_naming("Critical")
    assert "GV.OC-04" in definitions and "ID.RA-10" in definitions, definitions
    assert _collides("subcategory_definitions", definitions, "Critical")
    code = next(iter(definitions))
    payload = {
        "subcategories": list(definitions),
        "subcategory_definitions": definitions,
        "answers": {code: {"notes": "Critical's CISO owns this review.", "maturity_tier": 2}},
    }

    sent, row = _invoke(db_session, payload, "Critical")

    assert sent[0]["subcategory_definitions"] == definitions
    assert json.dumps(sent[0]["subcategory_definitions"]) == json.dumps(definitions)
    notes = sent[0]["answers"][code]["notes"]
    assert notes == "[CLIENT]'s CISO owns this review.", "client data is still redacted"
    # Catalog text is not counted as a client-name removal; the notes hit is.
    assert row.redacted_counts == {"client_org": 1}


# --- ZT: `capability_details`, orgs "DoD" and "Data" -------------------------


def _zt_details(codes: list[str]) -> dict[str, dict]:
    """The shape #981's `_zt_capability_details` sends for DoD, from the
    catalog's public accessors: the expected value, never the route's builder."""
    from app.zt.catalog import capability_by_code, pillar_by_code
    from app.zt.maturity import ZtFrameworkCode

    out: dict[str, dict] = {}
    for code in codes:
        cap = capability_by_code(code)
        out[code] = {
            "pillar": pillar_by_code(ZtFrameworkCode.DOD_ZTRA, cap.pillar_code).name,
            "name": cap.name,
            "activities": [
                {"id": a.id, "name": a.name, "level": a.level, "description": a.description}
                for a in cap.activities
            ],
        }
    return out


@pytest.mark.parametrize("org", ["DoD", "Data"])
def test_zt_capability_details_reach_the_model_unchanged(db_session, org) -> None:
    import app.routes.zt  # noqa: F401  (registers the field, as the app does)
    from app.zt.catalog import capabilities
    from app.zt.maturity import ZtFrameworkCode

    codes = [c.code for c in capabilities(ZtFrameworkCode.DOD_ZTRA)]
    details = _zt_details(codes)
    assert _collides("capability_details", details, org)
    payload = {
        "framework": "dod_ztra",
        "capability_details": details,
        "answers": {codes[0]: {"notes": f"{org} staff run this weekly.", "current": 2}},
    }

    sent, row = _invoke(db_session, payload, org)

    assert json.dumps(sent[0]["capability_details"]) == json.dumps(details)
    assert sent[0]["answers"][codes[0]]["notes"] == "[CLIENT] staff run this weekly."
    assert row.redacted_counts == {"client_org": 1}


# --- The guard ----------------------------------------------------------------


def test_a_registered_field_that_is_not_the_catalogs_text_is_refused_before_egress(
    db_session,
) -> None:
    """The exemption is for catalog text only. Client text under an exempt
    key would egress unredacted, so it is refused, loudly, and nothing is sent."""
    import app.routes.csf  # noqa: F401

    definitions = _csf_definitions_naming("Critical")
    code = next(iter(definitions))
    tampered = {**definitions, code: "Critical Corp's own notes."}
    with pytest.raises(CatalogFieldMismatch, match="subcategory_definitions"):
        _invoke(db_session, {"subcategory_definitions": tampered}, "Critical")
    assert db_session.execute(select(LLMCall)).scalars().all() == []


def test_a_code_the_catalog_does_not_have_is_refused(db_session) -> None:
    import app.routes.csf  # noqa: F401

    with pytest.raises(CatalogFieldMismatch, match="subcategory_definitions"):
        _invoke(db_session, {"subcategory_definitions": {"ZZ.ZZ-99": "x"}}, "Acme")


def test_an_unregistered_field_is_redacted_as_before() -> None:
    """Exemption is opt-in by registration: anything else is client data."""
    out, counts = redact_ai_payload(
        {"other": "Critical objectives"},
        mode="strict",
        client_org_name="Critical",
        name_hints=(),
    )
    assert out == {"other": "[CLIENT] objectives"}
    assert counts == {"client_org": 1}


def test_a_field_cannot_be_registered_twice_with_different_builders() -> None:
    import app.routes.csf  # noqa: F401

    with pytest.raises(ValueError, match="subcategory_definitions"):
        register_catalog_field("subcategory_definitions", lambda _p, v: v)


# --- CSF: the codes and tiers a request asks about (#986) -------------------


@pytest.mark.parametrize(
    ("org", "field"), [("GV", "subcategories"), ("ID", "subcategories"), ("High", "tiers")]
)
def test_csf_codes_and_tiers_reach_the_model_unchanged(db_session, org, field) -> None:
    import app.routes.csf  # noqa: F401
    from app.csf.catalog import SUBCATEGORIES

    codes = [s.code for s in SUBCATEGORIES]
    tiers = ["high", "low", "moderate"]
    assert _collides(field, codes if field == "subcategories" else tiers, org)
    payload = {
        "tiers": tiers,
        "subcategories": codes,
        "answers": {codes[0]: {"notes": f"{org} owns this.", "maturity_tier": 1}},
    }

    sent, row = _invoke(db_session, payload, org)

    assert sent[0]["subcategories"] == codes
    assert sent[0]["tiers"] == tiers
    assert sent[0]["answers"][codes[0]]["notes"] == "[CLIENT] owns this."
    assert row.redacted_counts == {"client_org": 1}


# --- ATT&CK: the technique codes (#986) ---------------------------------------


def test_attack_technique_codes_are_guarded(db_session) -> None:
    """No client name collides with an ATT&CK id (the phone rule's lookbehind
    keeps "T1003.001" whole), so there is no collision to prove here. The list
    is catalogue-sourced all the same, so it is sent verbatim and guarded: a
    code the catalogue does not have is refused, not sent."""
    import app.routes.attack  # noqa: F401  (registers the field, as the app does)

    codes = ["T1003", "T1003.001", "T1566"]
    sent, row = _invoke(db_session, {"technique_codes": codes}, "Acme")
    assert sent[0]["technique_codes"] == codes
    with pytest.raises(CatalogFieldMismatch, match="technique_codes"):
        _invoke(db_session, {"technique_codes": ["T9999"]}, "Acme")


# --- The refusal never carries the entry's value ------------------------------


def test_a_rebuild_failure_names_the_field_index_and_type_never_the_value(
    db_session, caplog, capsys
) -> None:
    """If client text ever reached a registered key, the refusal must not copy
    it into the exception, the user's message or the logs. Only the field, the
    entry's position and its type."""
    import app.routes.attack  # noqa: F401

    token = "ZEBRA-PRIVATE-NOTE-7731"
    with pytest.raises(CatalogFieldMismatch) as info:
        _invoke(db_session, {"technique_codes": ["T1003", token]}, "Acme")

    err = info.value
    assert err.field == "technique_codes"
    assert str(err) == (
        "payload field 'technique_codes' could not be rebuilt from the catalog "
        "before redaction (entry 1, a str); nothing was sent"
    )
    assert err.__cause__ is None and err.__context__ is None, "nothing chained"
    captured = capsys.readouterr()
    assert token not in str(err)
    assert token not in caplog.text
    assert token not in captured.out + captured.err
