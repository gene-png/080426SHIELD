"""csf_score Run-AI: dimension suggestions, validation, lock-skip (Work Order D4)."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.llm import FixtureProvider, LLMClient, LLMResponse
from app.csf.catalog import SUBCATEGORIES


@pytest.fixture()
def app_client(tmp_path) -> Iterator[tuple[TestClient, FixtureProvider]]:
    url = f"sqlite:///{tmp_path / 'shield-csfai.db'}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    from app.db.session import get_db
    from app.main import create_app
    from app.models.client import Client as _Client
    from app.models.client_domain import ClientDomain as _ClientDomain
    from app.routes.csf import _llm_dep

    def override_get_db() -> Iterator[Session]:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    provider = FixtureProvider()
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_llm_dep] = lambda: LLMClient(provider)
    _seed = TestSession()
    tenant = _Client(legal_name="Test Tenant")
    _seed.add(tenant)
    _seed.flush()
    _seed.add(_ClientDomain(client_id=tenant.id, domain="example.com"))
    _seed.commit()
    cid = str(tenant.id)
    with TestClient(app, headers={"X-Client-Id": cid}) as c:
        yield c, provider


def _bootstrap(c: TestClient) -> tuple[dict, str]:
    r = c.post(
        "/auth/register",
        json={
            "email": "admin@example.com",
            "password": "correct horse battery staple!",
            "display_name": "A",
        },
    )
    h = {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}
    svc_id = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"}).json()[
        "id"
    ]
    c.post(f"/csf/services/{svc_id}/assessments", headers=h)
    c.post(f"/csf/services/{svc_id}/profiles/seed", headers=h, json={"tiers": ["high"]})
    return h, svc_id


@pytest.mark.unit
def test_csf_run_ai_applies_dimensions_and_clamps(app_client) -> None:
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    code = SUBCATEGORIES[0].code
    provider.register_static(
        "csf_score",
        LLMResponse(
            '{"scores": [{"tier": "high", "subcategory_code": "' + code + '",'
            ' "governance": 2, "policy": 1, "implementation": 2, "monitoring": 1,'
            ' "improvement": 5, "what_we_found": "Mature IAM."}]}'  # improvement=5 invalid
        ),
    )
    r = c.post(f"/csf/services/{svc_id}/run-ai", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    row = next(x for x in body["rows"] if x["subcategory_code"] == code and x["tier"] == "high")
    assert row["governance"] == 2
    assert row["policy"] == 1
    assert row["implementation"] == 2
    assert row["improvement"] == 0  # out-of-range 5 ignored, stays default 0
    assert row["what_we_found"] == "Mature IAM."
    fields = {ch["field"] for ch in body["changed"] if ch["subcategory_code"] == code}
    assert {"governance", "policy", "implementation", "monitoring", "what_we_found"} <= fields


@pytest.mark.unit
def test_csf_run_ai_skips_locked(app_client) -> None:
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    code = SUBCATEGORIES[0].code
    rows = c.get(f"/csf/services/{svc_id}/profile/high", headers=h).json()["rows"]
    sid = next(x["id"] for x in rows if x["subcategory_code"] == code)
    c.patch(f"/csf/dimension-scores/{sid}", headers=h, json={"locked": True})
    provider.register_static(
        "csf_score",
        LLMResponse(
            '{"scores": [{"tier": "high", "subcategory_code": "' + code + '", "governance": 2}]}'
        ),
    )
    r = c.post(f"/csf/services/{svc_id}/run-ai", headers=h)
    row = next(x for x in r.json()["rows"] if x["subcategory_code"] == code and x["tier"] == "high")
    assert row["governance"] == 0
    assert all(ch["subcategory_code"] != code for ch in r.json()["changed"])


@pytest.mark.unit
def test_csf_run_ai_payload_carries_interview_answers(app_client) -> None:
    """Sprint 3 T0(b): the job payload must ground the model in the client's
    interview answers/evidence (not just tier/subcategory codes)."""
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    code = SUBCATEGORIES[0].code
    # Capture what actually reaches the provider (post-redaction send payload).
    captured: dict = {}

    def _capture(payload: dict) -> LLMResponse:
        captured.clear()
        captured.update(payload)
        return LLMResponse('{"scores": []}')

    provider.register("csf_score", _capture)

    # Give one subcategory real interview signal: a self-assessed tier + notes.
    latest = c.get(f"/csf/services/{svc_id}/assessments/latest", headers=h).json()
    answer_id = next(a["id"] for a in latest["answers"] if a["subcategory_code"] == code)
    r = c.patch(
        f"/csf/answers/{answer_id}",
        headers=h,
        json={"maturity_tier": 3, "notes": "Documented IAM policy exists."},
    )
    assert r.status_code == 200, r.text

    assert c.post(f"/csf/services/{svc_id}/run-ai", headers=h).status_code == 200
    assert "answers" in captured, "run-ai payload omitted interview answers"
    assert code in captured["answers"], "the answered subcategory is missing from the payload"
    ans = captured["answers"][code]
    assert ans["maturity_tier"] == 3
    assert ans["notes"] == "Documented IAM policy exists."
    assert ans["has_evidence"] is False
    # Unanswered subcategories are NOT flooded into the payload (only signal).
    assert len(captured["answers"]) == 1
    # Grounding is additive: the tier/subcategory context the fixture reads stays.
    assert "tiers" in captured and "subcategories" in captured


@pytest.mark.unit
def test_csf_run_ai_requires_seeded_profile(app_client) -> None:
    c, provider = app_client
    r = c.post(
        "/auth/register",
        json={
            "email": "admin@example.com",
            "password": "correct horse battery staple!",
            "display_name": "A",
        },
    )
    h = {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}
    svc_id = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"}).json()[
        "id"
    ]
    c.post(f"/csf/services/{svc_id}/assessments", headers=h)
    provider.register_static("csf_score", LLMResponse('{"scores": []}'))
    # No profile seeded -> 409.
    assert c.post(f"/csf/services/{svc_id}/run-ai", headers=h).status_code == 409


# --------------------------------------------------------------------------- #
# A failed AI call must leave evidence and a usable error.
#
# Found by the 2026-08-04 live run: a provider failure propagated as an
# unhandled exception, FastAPI returned a bare 500, and the rollback took the
# llm_calls row with it. Three real Anthropic calls consumed tokens and left
# ZERO rows behind. The workspace sat on "Running…" forever because no typed
# error ever reached it.
# --------------------------------------------------------------------------- #


def _raise_provider_error(_payload):
    raise RuntimeError("Anthropic did not finish cleanly (stop_reason=max_tokens).")


@pytest.mark.unit
def test_run_ai_provider_failure_returns_typed_error(app_client) -> None:
    """The client gets a typed D-016 error it can render, not a bare 500."""
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    provider.register("csf_score", _raise_provider_error)

    r = c.post(f"/csf/services/{svc_id}/run-ai", headers=h)

    assert r.status_code == 502, r.text
    err = r.json()["error"]
    assert err["reason"] == "ai_call_failed"
    assert "cut off" in err["message"], err["message"]
    # The UI has to be able to say whether money may have been spent.
    assert err["charged_likely"] is False  # fixture provider — no egress


@pytest.mark.unit
def test_run_ai_provider_failure_persists_the_llm_call_row(app_client) -> None:
    """The FAILED llm_calls row must survive the request.

    Asserted against the database through an INDEPENDENT session, because the
    defect being pinned is precisely that the request transaction rolled the row
    back — an assertion made through the request's own session would not see it.
    """
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    provider.register("csf_score", _raise_provider_error)

    r = c.post(f"/csf/services/{svc_id}/run-ai", headers=h)
    assert r.status_code == 502

    from app.models.llm_call import LLMCall, LLMCallStatus

    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    with sessionmaker(bind=engine, future=True)() as check:
        rows = check.execute(select(LLMCall)).scalars().all()
    failed = [x for x in rows if x.status == LLMCallStatus.FAILED]
    assert failed, "a failed provider call left no audit row at all"
    assert failed[0].purpose == "csf_score"
    assert failed[0].error_message
    assert failed[0].duration_ms is not None


@pytest.mark.unit
def test_run_ai_unwrapped_list_response_fails_loudly_not_silently(app_client) -> None:
    """Issue #41. A top-level array used to be flattened to `{}` at csf.py:1499.

    The run then reported zero changes with no warning anywhere — the exact
    "reads as total agreement" shape this engagement keeps finding. It must be a
    typed error the workspace can render, not a clean-looking no-op.
    """
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    provider.register_static(
        "csf_score",
        LLMResponse('[{"tier": "high", "subcategory_code": "GV.OC-01", "governance": 2}]'),
    )

    r = c.post(f"/csf/services/{svc_id}/run-ai", headers=h)

    assert r.status_code == 502, r.text
    err = r.json()["error"]
    assert err["reason"] == "ai_call_failed"
    # Assert on wording only the new `friendly_reason` branch supplies. The
    # generic fallback embeds the raw exception, which already contains
    # "object" — so asserting that would pass with the branch deleted.
    assert "drifted apart" in err["message"], err["message"]


# --------------------------------------------------------------------------
# W1 (issue #44) — dropped suggestions are itemized, per reason, and counted.
#
# The unit is ONE SUGGESTED VALUE: one field the model asked to set on one row.
# Entry-level drops (`entry_shape`, `unknown_key`, `locked`) fail before any
# single value can be blamed, so each states how many values it accounts for in
# `values` rather than defaulting to 1 — a fully-rejected row must not count the
# same as a single bad field. That makes the invariant a sum, not a length:
#
#     suggestions_received == suggestions_applied + sum(d.values for d in dropped)
# --------------------------------------------------------------------------

# Five dimensions + what_we_found. The width of one row's worth of suggestions,
# used when an entry is too broken to enumerate what it meant to set.
_ROW_VALUE_SLOTS = 6


def _run_ai(c, provider, h, svc_id, scores: list) -> dict:
    provider.register_static("csf_score", LLMResponse(json.dumps({"scores": scores})))
    r = c.post(f"/csf/services/{svc_id}/run-ai", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _assert_invariant(body: dict) -> None:
    """Every suggestion the run received is either applied or itemized."""
    accounted = body["suggestions_applied"] + sum(d["values"] for d in body["dropped"])
    assert body["suggestions_received"] == accounted, body


def _only_dropped(body: dict) -> dict:
    assert len(body["dropped"]) == 1, body["dropped"]
    return body["dropped"][0]


def _row(body: dict, code: str, tier: str = "high") -> dict:
    """The refreshed row, so a test can prove the value did NOT land.

    A correct-looking `dropped` record says nothing about the database. Asserting
    only the record leaves a regression that writes the value AND itemizes the
    drop looking perfectly green — the reason every value-level drop test below
    reads the row back. Seeded rows start at 0 with a null narrative.
    """
    return next(x for x in body["rows"] if x["subcategory_code"] == code and x["tier"] == tier)


@pytest.mark.unit
def test_csf_run_ai_counts_each_value_and_holds_the_invariant(app_client) -> None:
    """The headline: a mixed response is fully accounted for, per value."""
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    code = SUBCATEGORIES[0].code
    body = _run_ai(
        c,
        provider,
        h,
        svc_id,
        [
            {"tier": "high", "subcategory_code": code, "governance": 2, "improvement": 5},
            {"tier": "high", "subcategory_code": "GV.OC-1", "governance": 2},
            "not-a-dict",
        ],
    )

    # governance=2 landed; improvement=5 is out of range; GV.OC-1 is a typo for
    # a real code; the bare string cannot be read at all.
    assert body["suggestions_applied"] == 1
    assert body["suggestions_received"] == 2 + 1 + _ROW_VALUE_SLOTS
    _assert_invariant(body)
    assert {d["reason"] for d in body["dropped"]} == {
        "out_of_range",
        "unknown_key",
        "entry_shape",
    }


@pytest.mark.unit
def test_csf_run_ai_unknown_key_is_itemized_verbatim(app_client) -> None:
    """`{"reason": "unknown_key", "key": "high|GV.OC-1"}` tells a consultant
    instantly that the catalogue holds GV.OC-01. A bare count tells them nothing.
    """
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    body = _run_ai(
        c, provider, h, svc_id, [{"tier": "high", "subcategory_code": "GV.OC-1", "governance": 2}]
    )

    d = _only_dropped(body)
    assert d["reason"] == "unknown_key"
    assert d["key"] == "high|GV.OC-1"
    assert body["suggestions_applied"] == 0
    _assert_invariant(body)


@pytest.mark.unit
def test_csf_run_ai_absent_keys_are_never_reported_as_the_string_none(app_client) -> None:
    """`f"{tier}|{code}"` yields the literal "None|None" when the model omits
    both keys. Reporting that as the key the model wrote is a fabrication — it
    names a row nobody asked for. Absence must read as absence.
    """
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    body = _run_ai(c, provider, h, svc_id, [{"governance": 2}])

    d = _only_dropped(body)
    assert d["reason"] == "unknown_key"
    assert d["key"] != "None|None"
    assert d["key"] is None
    _assert_invariant(body)


@pytest.mark.unit
def test_csf_run_ai_locked_is_a_distinct_reason_from_unknown_key(app_client) -> None:
    """`if row is None or row.locked: continue` merged "the model named a row
    that does not exist" with "a human locked this". The first is a defect; the
    second is the system working. They must not render as one number (#31).
    """
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    code = SUBCATEGORIES[0].code
    rows = c.get(f"/csf/services/{svc_id}/profile/high", headers=h).json()["rows"]
    sid = next(x["id"] for x in rows if x["subcategory_code"] == code)
    c.patch(f"/csf/dimension-scores/{sid}", headers=h, json={"locked": True})

    body = _run_ai(
        c, provider, h, svc_id, [{"tier": "high", "subcategory_code": code, "governance": 2}]
    )

    d = _only_dropped(body)
    assert d["reason"] == "locked"
    assert d["key"] == f"high|{code}"
    assert d["values"] == 1
    assert _row(body, code)["governance"] == 0  # the lock actually held
    _assert_invariant(body)


@pytest.mark.unit
def test_csf_run_ai_entry_level_drop_states_how_many_values_it_covers(app_client) -> None:
    """A rejected row carrying three suggestions is three lost values, not one.
    Counting it as one is the undercount a bare integer used to produce.
    """
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    body = _run_ai(
        c,
        provider,
        h,
        svc_id,
        [
            {
                "tier": "high",
                "subcategory_code": "GV.OC-1",
                "governance": 2,
                "policy": 1,
                "monitoring": 0,
            }
        ],
    )

    d = _only_dropped(body)
    assert d["reason"] == "unknown_key"
    assert d["values"] == 3
    assert body["suggestions_received"] == 3
    _assert_invariant(body)


@pytest.mark.unit
def test_csf_run_ai_unreadable_entry_counts_the_full_row_width(app_client) -> None:
    """A non-object entry cannot be enumerated — nothing in it can be read. It
    is charged the full width of a row rather than 1, so an unreadable response
    cannot look cheaper than a readable one that failed.
    """
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    body = _run_ai(c, provider, h, svc_id, ["not-a-dict"])

    d = _only_dropped(body)
    assert d["reason"] == "entry_shape"
    assert d["values"] == _ROW_VALUE_SLOTS
    assert d["key"] is None
    _assert_invariant(body)


@pytest.mark.unit
def test_csf_run_ai_entry_naming_a_real_row_with_no_values_is_not_silent(app_client) -> None:
    """A dict that resolves to a real row but carries no recognized field would
    apply nothing and drop nothing — it would vanish from both sides of the
    invariant and satisfy it vacuously. It is charged as an unusable entry.
    """
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    code = SUBCATEGORIES[0].code
    body = _run_ai(c, provider, h, svc_id, [{"tier": "high", "subcategory_code": code}])

    d = _only_dropped(body)
    assert d["reason"] == "entry_shape"
    # `> 0` would pass if this charged 1 instead of the full row width, which is
    # the exact rule the docstring claims to pin.
    assert d["values"] == _ROW_VALUE_SLOTS
    assert body["suggestions_received"] == _ROW_VALUE_SLOTS
    _assert_invariant(body)


@pytest.mark.unit
def test_csf_run_ai_unparseable_value_names_its_field(app_client) -> None:
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    code = SUBCATEGORIES[0].code
    body = _run_ai(
        c, provider, h, svc_id, [{"tier": "high", "subcategory_code": code, "governance": "two"}]
    )

    d = _only_dropped(body)
    assert d["reason"] == "unparseable"
    assert d["field"] == "governance"
    assert d["values"] == 1
    assert _row(body, code)["governance"] == 0  # itemized AND not written
    _assert_invariant(body)


@pytest.mark.unit
def test_csf_run_ai_out_of_range_value_names_its_field(app_client) -> None:
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    code = SUBCATEGORIES[0].code
    body = _run_ai(
        c, provider, h, svc_id, [{"tier": "high", "subcategory_code": code, "improvement": 5}]
    )

    d = _only_dropped(body)
    assert d["reason"] == "out_of_range"
    assert d["field"] == "improvement"
    assert d["values"] == 1
    assert _row(body, code)["improvement"] == 0  # itemized AND not written
    _assert_invariant(body)


@pytest.mark.unit
def test_csf_run_ai_non_string_narrative_is_itemized_not_dropped_silently(app_client) -> None:
    """`if isinstance(sugg.get("what_we_found"), str)` skipped a non-string
    narrative without a trace. It is a suggested value like any other.
    """
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    code = SUBCATEGORIES[0].code
    body = _run_ai(
        c, provider, h, svc_id, [{"tier": "high", "subcategory_code": code, "what_we_found": 42}]
    )

    d = _only_dropped(body)
    assert d["reason"] == "wrong_type"
    assert d["field"] == "what_we_found"
    assert d["values"] == 1
    assert _row(body, code)["what_we_found"] is None  # itemized AND not written
    _assert_invariant(body)


@pytest.mark.unit
def test_csf_run_ai_misnamed_field_is_counted_not_silently_ignored(app_client) -> None:
    """The defect an adversarial pass found in the first cut of this feature.

    `fields = [f for f in _RUN_FIELDS if f in sugg]` enumerated only keys the
    parser already recognized, so a field the model named differently vanished
    from BOTH sides of the invariant: received and applied agreed, dropped was
    empty, and the panel asserted full accounting over the loss.

    It is not hypothetical. The csf_score prompt names the dimensions in prose
    as "Policy and Process" / "Monitoring and Measurement" / "Continuous
    Improvement" while its JSON example uses policy / monitoring / improvement.
    A count that only sees what it already understands cannot detect drift —
    which is the one thing it exists to detect.
    """
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    code = SUBCATEGORIES[0].code
    body = _run_ai(
        c,
        provider,
        h,
        svc_id,
        [
            {
                "tier": "high",
                "subcategory_code": code,
                "governance": 2,
                "policy_and_process": 1,
                "monitoring_and_measurement": 1,
                "continuous_improvement": 0,
            }
        ],
    )

    assert body["suggestions_applied"] == 1  # governance only
    assert body["suggestions_received"] == 4
    _assert_invariant(body)
    drift = [d for d in body["dropped"] if d["reason"] == "unknown_field"]
    assert len(drift) == 3, body["dropped"]
    # The NAME is the whole diagnostic — it is what shows prompt/parser drift.
    assert {d["field"] for d in drift} == {
        "policy_and_process",
        "monitoring_and_measurement",
        "continuous_improvement",
    }


@pytest.mark.unit
def test_csf_run_ai_scores_nested_under_one_strange_key_are_all_counted(app_client) -> None:
    """The FIX for the misnamed-field defect re-opened it, one layer down.

    Guarding with `if not fields and not unknown_fields` meant a single
    unrecognized key suppressed the full-row-width charge and substituted a
    charge of one — so five scores wearing one wrapper key were counted on
    NEITHER side, and `received == applied + sum(values)` held over them.

    An unreadable entry must never be cheaper to lose than a readable one that
    failed validation. A container is charged what it actually hides.
    """
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    code = SUBCATEGORIES[0].code
    body = _run_ai(
        c,
        provider,
        h,
        svc_id,
        [
            {
                "tier": "high",
                "subcategory_code": code,
                "dimensions": {
                    "governance": 2,
                    "policy": 1,
                    "implementation": 1,
                    "monitoring": 0,
                    "improvement": 2,
                },
            }
        ],
    )

    d = _only_dropped(body)
    assert d["reason"] == "unknown_field"
    assert d["field"] == "dimensions"
    assert d["values"] == 5, "a wrapper hiding five scores must not be charged one"
    assert body["suggestions_received"] == 5
    assert body["suggestions_applied"] == 0
    _assert_invariant(body)


@pytest.mark.unit
def test_csf_run_ai_half_written_key_is_not_reported_as_a_row_named_none(app_client) -> None:
    """The "None|None" fix was only half a fix: the guard was `tier is None AND
    code is None`, so a model that wrote one half produced "high|None", which a
    consultant reads as a subcategory literally called None.
    """
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    body = _run_ai(c, provider, h, svc_id, [{"tier": "high", "governance": 2}])

    d = _only_dropped(body)
    assert d["reason"] == "unknown_key"
    assert "None" not in d["key"], d["key"]
    assert "high" in d["key"] and "missing" in d["key"], d["key"]
    _assert_invariant(body)


@pytest.mark.unit
def test_csf_run_ai_superseded_value_is_not_counted_as_applied(app_client) -> None:
    """Two entries for the same row+field: the first never reaches the client.

    Counting both as applied reports more values landed than the row holds — a
    surfaced number that is wrong, which PR #39 established is worse than none.
    """
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    code = SUBCATEGORIES[0].code
    body = _run_ai(
        c,
        provider,
        h,
        svc_id,
        [
            {"tier": "high", "subcategory_code": code, "governance": 2},
            {"tier": "high", "subcategory_code": code, "governance": 0},
        ],
    )

    assert body["suggestions_received"] == 2
    assert body["suggestions_applied"] == 1  # only the value the row now holds
    d = _only_dropped(body)
    assert d["reason"] == "superseded"
    assert d["field"] == "governance"
    _assert_invariant(body)
    row = next(x for x in body["rows"] if x["subcategory_code"] == code and x["tier"] == "high")
    assert row["governance"] == 0


@pytest.mark.unit
def test_csf_run_ai_out_of_range_shows_what_the_model_wrote(app_client) -> None:
    """The record whose job is to show what the model said reported the COERCED
    value: `{"governance": 3.9}` was itemized as 3, and `"7"` as 7.
    """
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    code = SUBCATEGORIES[0].code
    body = _run_ai(
        c, provider, h, svc_id, [{"tier": "high", "subcategory_code": code, "governance": 3.9}]
    )

    d = _only_dropped(body)
    assert d["reason"] == "out_of_range"
    assert "3.9" in str(d["value"]), d["value"]
    # Range is judged BEFORE wholeness on purpose: 3.9 is both out of range and
    # not a whole number, and the range is the more useful thing to report.
    assert _row(body, code)["governance"] == 0
    _assert_invariant(body)


@pytest.mark.unit
def test_csf_run_ai_in_range_float_is_refused_not_silently_truncated(app_client) -> None:
    """The last place in this path where a value changed with NO record.

    `int(1.9)` is 1, in range, so it was written to the row, counted as applied
    and itemized nowhere. The model said 1.9, the client's Playbook said 1, and
    the accounting asserted full fidelity over the difference — silent handling
    inside the mechanism built to end silent handling.

    Its sibling `3.9` was already tested, but only because it is out of RANGE.
    The suite pinned the doctrine exactly where the code upheld it and nowhere
    it broke it.
    """
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    code = SUBCATEGORIES[0].code
    body = _run_ai(
        c, provider, h, svc_id, [{"tier": "high", "subcategory_code": code, "governance": 1.9}]
    )

    d = _only_dropped(body)
    assert d["reason"] == "unparseable"
    assert d["field"] == "governance"
    assert "1.9" in str(d["value"]), d["value"]
    assert body["suggestions_applied"] == 0
    assert _row(body, code)["governance"] == 0
    _assert_invariant(body)


@pytest.mark.unit
def test_csf_run_ai_boolean_is_not_a_score_of_one(app_client) -> None:
    """`bool` is an `int` subclass, so `int(True)` is 1 and lands in range. A
    model answering `true` was recorded as having suggested a score of 1.
    """
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    code = SUBCATEGORIES[0].code
    body = _run_ai(
        c, provider, h, svc_id, [{"tier": "high", "subcategory_code": code, "policy": True}]
    )

    d = _only_dropped(body)
    assert d["reason"] == "unparseable"
    assert d["field"] == "policy"
    assert _row(body, code)["policy"] == 0
    _assert_invariant(body)


@pytest.mark.unit
def test_csf_run_ai_whole_number_written_as_text_or_float_is_applied(app_client) -> None:
    """The other half of the rule, or it is just strictness.

    `"2"` and `2.0` are whole numbers written differently. Refusing them would
    throw away a value the model plainly meant — the #31 failure in the other
    direction, where the guard against silent loss becomes a source of it.
    """
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    code = SUBCATEGORIES[0].code
    body = _run_ai(
        c,
        provider,
        h,
        svc_id,
        [{"tier": "high", "subcategory_code": code, "policy": "2", "monitoring": 1.0}],
    )

    assert body["dropped"] == []
    assert body["suggestions_applied"] == 2
    row = _row(body, code)
    assert row["policy"] == 2
    assert row["monitoring"] == 1
    _assert_invariant(body)


@pytest.mark.unit
def test_csf_run_ai_logs_carry_no_key_and_no_model_text(app_client, capsys) -> None:
    """CONSTRAINT 1 rule 3, which nothing previously pinned.

    `zt.py` already logs `value=repr(raw)[:120]` — pre-existing debt W1's ZT step
    must revisit. Adding `key=` or `value=` to this run's log would be a one-line
    §12.1 violation that every other test in this file would still pass.

    Reads stdout, not `caplog`: structlog renders JSON straight to stdout here,
    so the stdlib logging capture sees nothing and an assertion built on it would
    pass over any content whatsoever.
    """
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    _run_ai(
        c,
        provider,
        h,
        svc_id,
        [
            {
                "tier": "high",
                "subcategory_code": "GV.OC-1",
                "what_we_found": "ACME uses Okta",
                # A FIELD NAME the model invented. `dropped[].field` is a third
                # model-generated string, added when the drift diagnostic moved
                # above the row lookup, and the payload here had no unrecognized
                # key at all — so logging the drifted names would have been a
                # §12.1 leak this test was written to catch and could not see.
                "okta_governance": 2,
            }
        ],
    )

    text = capsys.readouterr().out
    assert "csf_run_ai_suggestions_accounted" in text, "the accounting must be logged at all"
    assert "GV.OC-1" not in text, text
    assert "Okta" not in text, text
    assert "okta_governance" not in text, text


@pytest.mark.unit
def test_csf_run_ai_non_list_scores_is_an_error_not_a_pile_of_drops(app_client) -> None:
    """`{"scores": "..."}` passes `parse_json_object` — the top level IS an
    object — and then the loop iterates the string one CHARACTER at a time,
    manufacturing an unreadable "entry" per character. The invariant would hold
    over a total built entirely out of noise.

    Issue #44's own rule: a condition that can never coexist with an applied
    suggestion is an error, not a per-item drop.
    """
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    provider.register_static("csf_score", LLMResponse('{"scores": "GV.OC-01 looks fine"}'))

    r = c.post(f"/csf/services/{svc_id}/run-ai", headers=h)

    assert r.status_code == 502, r.text
    assert r.json()["error"]["reason"] == "ai_call_failed"
    assert "drifted apart" in r.json()["error"]["message"]


@pytest.mark.unit
def test_csf_run_ai_audit_row_carries_counts_but_no_model_content(app_client) -> None:
    """CONSTRAINT 1 (#44). `key` and `value` are model-generated strings and the
    model was fed the client's own tiers and notes, so it can echo client data
    back. The audit row is a durable store outside both the artifact mechanism
    and Master Spec §12.1: reason codes and counts ONLY.
    """
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    # THREE values on ONE rejected entry, so `dropped_by_reason` cannot pass by
    # counting records — 3 discriminates values-per-reason from entries-per-
    # reason, where a single-value entry would read as 1 under either rule.
    body = _run_ai(
        c,
        provider,
        h,
        svc_id,
        [
            {
                "tier": "high",
                "subcategory_code": "GV.OC-1",
                "governance": 2,
                "policy": 1,
                "what_we_found": "ACME uses Okta",
                # A model-invented FIELD name, so the drifted-name surface is
                # covered too — it reaches `dropped[].field` in the response and
                # must not reach this durable row.
                "okta_governance": 2,
            }
        ],
    )
    # The API response may carry it — same trust boundary as the run result.
    unresolved = next(d for d in body["dropped"] if d["reason"] == "unknown_key")
    assert unresolved["key"] == "high|GV.OC-1"
    assert unresolved["values"] == 3

    from app.models.audit_entry import AuditEntry

    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    with sessionmaker(bind=engine, future=True)() as check:
        entry = check.execute(
            select(AuditEntry).where(AuditEntry.action == "csf.run_ai")
        ).scalar_one()
        details = json.dumps(entry.details)
        assert entry.details["suggestions_received"] == 4
        assert entry.details["suggestions_applied"] == 0
        # Values, not records — so the durable row can check its own arithmetic.
        assert entry.details["dropped_by_reason"] == {"unknown_key": 3, "unknown_field": 1}
        assert entry.details["suggestions_received"] == entry.details["suggestions_applied"] + sum(
            entry.details["dropped_by_reason"].values()
        )
        # Neither the verbatim key, the drifted field name, nor any model text
        # reaches the durable row — reason codes and counts ONLY.
        assert "GV.OC-1" not in details, details
        assert "Okta" not in details, details
        assert "okta_governance" not in details, details


# --------------------------------------------------------------------------
# W1 round 3. Three adversarial passes over the working tree found these. Each
# case below FAILED against the implementation as first written, or pins a
# promise the suite had asserted only in prose.
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_csf_run_ai_misnamed_row_key_still_names_the_field_that_drifted(app_client) -> None:
    """The drift signal must survive a row that does not resolve.

    A model that writes `code` instead of `subcategory_code` IS the Sprint 3 T0
    drift. The row then cannot be found, and the first cut returned at
    `if row is None` before itemizing field names — discarding the one piece of
    evidence saying the model used a key called `code`. Over a seeded Playbook
    that is 318 identical "no matching row" bullets sending a consultant to hunt
    a seeding fault that does not exist.
    """
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    code = SUBCATEGORIES[0].code
    body = _run_ai(
        c, provider, h, svc_id, [{"tier": "high", "code": code, "governance": 2, "policy": 1}]
    )

    assert {d["reason"] for d in body["dropped"]} == {"unknown_field", "unknown_key"}
    drift = next(d for d in body["dropped"] if d["reason"] == "unknown_field")
    assert drift["field"] == "code"
    # The recognized values are charged once, to the unresolvable row, and not
    # again to the drift record — or the entry is counted twice on one side.
    unresolved = next(d for d in body["dropped"] if d["reason"] == "unknown_key")
    assert unresolved["values"] == 2
    assert body["suggestions_received"] == 3
    _assert_invariant(body)


@pytest.mark.unit
def test_csf_run_ai_locked_row_still_reports_field_drift(app_client) -> None:
    """The stated blind spot, now closed rather than merely documented.

    Charging a locked row wholly to `locked` made prompt/parser drift inside it
    invisible. The row was never going to be written, but the DRIFT is a fact
    about the prompt, not about this row — and a Playbook whose interesting rows
    are all locked would have reported no drift at all.
    """
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    code = SUBCATEGORIES[0].code
    rows = c.get(f"/csf/services/{svc_id}/profile/high", headers=h).json()["rows"]
    sid = next(x["id"] for x in rows if x["subcategory_code"] == code)
    c.patch(f"/csf/dimension-scores/{sid}", headers=h, json={"locked": True})

    body = _run_ai(
        c,
        provider,
        h,
        svc_id,
        [{"tier": "high", "subcategory_code": code, "governance": 2, "policy_and_process": 1}],
    )

    assert {d["reason"] for d in body["dropped"]} == {"unknown_field", "locked"}
    drift = next(d for d in body["dropped"] if d["reason"] == "unknown_field")
    assert drift["field"] == "policy_and_process"
    assert _row(body, code)["governance"] == 0  # the lock still held
    _assert_invariant(body)


@pytest.mark.unit
def test_csf_run_ai_container_under_a_recognized_key_is_counted_whole(app_client) -> None:
    """The vacuous hold, left open one key over.

    `_hidden_value_count` was applied only to UNRECOGNIZED keys; recognized ones
    were charged a flat 1 each. Three scores wearing a recognized name were
    counted as one, itemized as one, and `_assert_invariant` passed over the
    undercount — the identical failure the wrapper-key test forbids next door.
    """
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    code = SUBCATEGORIES[0].code
    body = _run_ai(
        c,
        provider,
        h,
        svc_id,
        [
            {
                "tier": "high",
                "subcategory_code": code,
                "governance": {"high": 2, "moderate": 1, "low": 0},
            }
        ],
    )

    d = _only_dropped(body)
    assert d["reason"] == "unparseable"
    assert d["field"] == "governance"
    assert d["values"] == 3, d
    assert body["suggestions_received"] == 3
    assert _row(body, code)["governance"] == 0
    _assert_invariant(body)


@pytest.mark.unit
def test_csf_run_ai_two_level_wrapper_counts_leaves_not_the_wrapper(app_client) -> None:
    """`len()` of a container stops at one level, so `{"dimensions": {…5…}}`
    nested one deeper was charged 1 and hid five — the vacuous hold the count
    exists to prevent, reappearing one nesting level below where it was fixed.
    """
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    code = SUBCATEGORIES[0].code
    body = _run_ai(
        c,
        provider,
        h,
        svc_id,
        [
            {
                "tier": "high",
                "subcategory_code": code,
                "values": {
                    "dimensions": {
                        "governance": 2,
                        "policy": 1,
                        "implementation": 1,
                        "monitoring": 0,
                        "improvement": 2,
                    }
                },
            }
        ],
    )

    d = _only_dropped(body)
    assert d["reason"] == "unknown_field"
    assert d["field"] == "values"
    assert d["values"] == 5, d
    assert body["suggestions_received"] == 5
    _assert_invariant(body)


@pytest.mark.unit
def test_csf_run_ai_narrative_supersede_path_is_exercised(app_client) -> None:
    """`what_we_found` takes a different branch from the five numeric fields, and
    its supersede guard was written but executed by no test in the suite.
    """
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    code = SUBCATEGORIES[0].code
    body = _run_ai(
        c,
        provider,
        h,
        svc_id,
        [
            {"tier": "high", "subcategory_code": code, "what_we_found": "first"},
            {"tier": "high", "subcategory_code": code, "what_we_found": "second"},
        ],
    )

    assert body["suggestions_received"] == 2
    assert body["suggestions_applied"] == 1
    d = _only_dropped(body)
    assert d["reason"] == "superseded"
    assert d["field"] == "what_we_found"
    assert _row(body, code)["what_we_found"] == "second"
    _assert_invariant(body)


@pytest.mark.unit
def test_csf_run_ai_same_field_on_two_rows_is_not_a_supersede(app_client) -> None:
    """`written` is keyed on (row, field). Keyed on `field` alone, every row
    after the first reports as superseded while its value lands correctly.
    """
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    a, b = SUBCATEGORIES[0].code, SUBCATEGORIES[1].code
    body = _run_ai(
        c,
        provider,
        h,
        svc_id,
        [
            {"tier": "high", "subcategory_code": a, "governance": 2},
            {"tier": "high", "subcategory_code": b, "governance": 2},
        ],
    )

    assert body["dropped"] == []
    assert body["suggestions_applied"] == 2
    assert _row(body, a)["governance"] == 2
    assert _row(body, b)["governance"] == 2
    _assert_invariant(body)


@pytest.mark.unit
def test_csf_run_ai_model_following_the_prompt_prose_loses_everything_loudly(app_client) -> None:
    """The realistic drift shape, not a hybrid.

    The existing drift test mixes three prose-derived names with `governance` in
    the parser's own spelling — a response no model would produce. A model that
    follows the prompt's PROSE ("Governance, Policy and Process, Implementation,
    Monitoring and Measurement, Continuous Improvement") drifts on all five,
    capitalisation included. Nothing is applied and every value must be named: a
    run that applied zero of five must never read as agreement.
    """
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    code = SUBCATEGORIES[0].code
    body = _run_ai(
        c,
        provider,
        h,
        svc_id,
        [
            {
                "tier": "high",
                "subcategory_code": code,
                "Governance": 2,
                "Policy and Process": 1,
                "Implementation": 1,
                "Monitoring and Measurement": 0,
                "Continuous Improvement": 2,
            }
        ],
    )

    assert body["suggestions_received"] == 5
    assert body["suggestions_applied"] == 0
    assert {d["reason"] for d in body["dropped"]} == {"unknown_field"}
    assert {d["field"] for d in body["dropped"]} == {
        "Governance",
        "Policy and Process",
        "Implementation",
        "Monitoring and Measurement",
        "Continuous Improvement",
    }
    _assert_invariant(body)


@pytest.mark.unit
def test_csf_run_ai_unresolvable_row_is_named_even_when_it_charges_nothing(app_client) -> None:
    """Round 3's own repair re-opened a hole, in the way round 2's did.

    Emitting the row-level record only `if recognized_values:` meant an entry
    that named an unseeded tier AND wrapped its scores under one strange key
    produced a single `unknown_field` and nothing else — and the panel routes
    that to the quiet block. The run reported a field-name curiosity and never
    said the tier does not exist. `values=0` is honest for a record whose job is
    to name the row rather than account for a value; the values are counted once,
    under the name they arrived with.
    """
    c, provider = app_client
    h, svc_id = _bootstrap(c)  # seeds the `high` tier only
    code = SUBCATEGORIES[0].code
    body = _run_ai(
        c,
        provider,
        h,
        svc_id,
        [
            {
                "tier": "moderate",
                "subcategory_code": code,
                "dimensions": {"governance": 2, "policy": 1, "implementation": 1},
            }
        ],
    )

    assert {d["reason"] for d in body["dropped"]} == {"unknown_field", "unknown_key"}
    unresolved = next(d for d in body["dropped"] if d["reason"] == "unknown_key")
    assert unresolved["key"] == f"moderate|{code}"
    assert unresolved["values"] == 0  # named, not double-charged
    assert body["suggestions_received"] == 3
    _assert_invariant(body)


@pytest.mark.unit
def test_csf_run_ai_absurdly_large_integer_is_itemized_not_a_500(app_client) -> None:
    """`float()` raises OverflowError, not ValueError, on a huge int literal.

    Uncaught, that is a bare 500 raised after `llm_calls` was flushed COMPLETED
    and before the commit — so the rollback destroys the egress record for a call
    the provider was already paid for. That is the N-019 shape: money spent,
    ledger empty. Implausible from a real model; the point is that no input
    reaches the caller as an untyped crash.
    """
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    code = SUBCATEGORIES[0].code
    body = _run_ai(
        c,
        provider,
        h,
        svc_id,
        [{"tier": "high", "subcategory_code": code, "governance": int("9" * 400)}],
    )

    d = _only_dropped(body)
    assert d["reason"] == "unparseable"
    assert d["field"] == "governance"
    assert _row(body, code)["governance"] == 0
    _assert_invariant(body)
