"""#802: the chat box's AI reading, through the parse route.

The plan is #802 comment 5981734020, section 1's fallback table; the advisor
approved it at 16:40Z (comment 5982109105) with N1 and N2 verbatim. The table
is written FIRST, one row per line, and the code is held to it:

| registered | page acknowledged | provider | rate limit | result | AI called | note |
| no         | live              | live     | ok         | matcher | no       | none |
| yes        | (none sent)       | live     | ok         | matcher | no       | none |
| yes        | offline           | live     | ok         | matcher | no       | none |
| yes        | live              | fixture  | ok         | matcher | no       | none |
| yes        | live              | live     | exceeded   | matcher | no       | N2   |
| yes        | live              | live     | ok         | AI      | yes      | none |
| yes        | live              | live     | ok, call fails | matcher | yes  | N2   |
| yes        | live              | live     | ok, answer out of shape | matcher | yes | N2 |

and before every row: a description the matcher understood whole never asks.
The world is slice A's: the base cites EDR Tool, SIEM Tool and SOAR Tool, and
the client is "Acme".
"""

from __future__ import annotations

import json

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.ai import engine as ai_engine
from app.ai.llm import FixtureProvider, LLMResponse
from app.attack import scenario_intent
from app.models.ai_run import AiRun
from app.models.attack_scenario import AttackScenario
from app.models.audit_entry import AuditEntry
from app.models.llm_call import LLMCall
from app.models.user import User, UserRole
from tests.unit.test_ai_runs_attack import (  # noqa: F401  (app_parts: fixture)
    LiveLookingProvider,
    app_parts,
)
from tests.unit.test_attack_scenario_routes import EDR, SIEM, SOAR, _error, _world

pytestmark = pytest.mark.unit

#: N2, approved verbatim at 16:40Z.
N2 = (
    "The AI could not read your description just now, so only the tools named exactly "
    "as listed were filled in."
)
#: A description the matcher leaves not understood.
VAGUE = "get rid of the edr thing"


@pytest.fixture
def intent_unregistered(monkeypatch) -> None:
    """The purpose as it was before its prompt was released. `monkeypatch`
    restores the real job afterwards; a bare pop would delete it for every
    later test (track4, #846)."""
    monkeypatch.delitem(ai_engine._REGISTRY, scenario_intent.PURPOSE)


class _Limited:
    def enforce_ai(self, client_id) -> None:
        raise HTTPException(status_code=429, detail={"reason": "rate_limited", "message": "x"})


def _provider(live: bool, answer, seen: list[dict]) -> FixtureProvider:
    provider = LiveLookingProvider() if live else FixtureProvider()

    def respond(payload: dict) -> LLMResponse:
        seen.append(payload)
        if isinstance(answer, Exception):
            # A FRESH exception per call, as a real provider raises: a shared
            # instance held by the parameters keeps its traceback, and every
            # object that traceback references, alive (#863 review, round 2).
            raise type(answer)(*answer.args)
        return LLMResponse(json.dumps(answer))

    provider.register(scenario_intent.PURPOSE, respond)
    return provider


def _parse(w, text, serves):
    body = {"text": text} if serves is None else {"text": text, "serves": serves}
    return w.c.post(f"/attack/services/{w.svc_id}/scenarios/parse", headers=w.h, json=body)


GOOD = {"remove": [EDR], "add": [], "unclear": []}


def test_an_answer_written_as_the_prompt_asks_fills_the_list(app_parts) -> None:  # noqa: F811
    """The fixture is authored from the PROMPT's words, not from the reader:
    a removal "copied EXACTLY as it appears in `tools`", an addition "named as
    the administrator wrote them", and the rest "quoted exactly as written"."""
    w = _world(app_parts)
    text = "swap the edr thing for XDR Suite, and tidy the dashboards"
    w.use(
        _provider(
            True,
            {"remove": [EDR], "add": ["XDR Suite"], "unclear": ["tidy the dashboards"]},
            [],
        )
    )
    r = _parse(w, text, "live")
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["source"], body["removed"], body["added"]) == ("ai", [EDR], ["XDR Suite"])
    assert [(n["text"], n["reason"], n["message"]) for n in body["not_understood"]] == [
        (
            "tidy the dashboards",
            "ai_unclear",
            'Not understood: "tidy the dashboards". Pick the tool from the list instead.',
        )
    ]


@pytest.mark.parametrize(
    ("registered", "serves", "live", "limited", "answer", "source", "note", "called"),
    [
        pytest.param(False, "live", True, False, GOOD, "matcher", None, False, id="unregistered"),
        pytest.param(True, None, True, False, GOOD, "matcher", None, False, id="no-serves"),
        pytest.param(True, "offline", True, False, GOOD, "matcher", None, False, id="ack-offline"),
        pytest.param(
            True, "live", False, False, GOOD, "matcher", None, False, id="fixture-provider"
        ),
        pytest.param(True, "live", True, True, GOOD, "matcher", N2, False, id="rate-limited"),
        pytest.param(True, "live", True, False, GOOD, "ai", None, True, id="ai-reads-it"),
        pytest.param(
            True, "live", True, False, RuntimeError("boom"), "matcher", N2, True, id="call-fails"
        ),
        pytest.param(
            True, "live", True, False, {"remove": [EDR]}, "matcher", N2, True, id="out-of-shape"
        ),
    ],
)
def test_the_fallback_table(
    app_parts,  # noqa: F811
    request,
    registered,
    serves,
    live,
    limited,
    answer,
    source,
    note,
    called,  # noqa: F811
) -> None:
    if not registered:
        request.getfixturevalue("intent_unregistered")
    w = _world(app_parts)
    seen: list[dict] = []
    w.use(_provider(live, answer, seen))
    if limited:
        from app.security.rate_limit import get_rate_limiter

        w.app.dependency_overrides[get_rate_limiter] = lambda: _Limited()
    r = _parse(w, VAGUE, serves)
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["source"], body["note"], bool(seen)) == (source, note, called)
    if source == "ai":
        assert (body["removed"], body["added"], body["not_understood"]) == ([EDR], [], [])
    else:
        assert body["removed"] == []
        assert [n["reason"] for n in body["not_understood"]] == ["unrecognised"]


def test_a_description_the_matcher_understood_never_asks(
    app_parts,  # noqa: F811
) -> None:
    w = _world(app_parts)
    seen: list[dict] = []
    w.use(_provider(True, GOOD, seen))
    r = _parse(w, "retire SIEM Tool", "live")
    assert r.status_code == 200, r.text
    assert (r.json()["source"], r.json()["removed"], seen) == ("matcher", [SIEM], [])


def test_an_acknowledgement_that_is_not_a_mode_is_a_typed_422(app_parts) -> None:  # noqa: F811
    w = _world(app_parts)
    r = _parse(w, VAGUE, "maybe")
    assert r.status_code == 422, r.text
    assert _error(r)["reason"] == "serves_required"


# --- what the AI is sent ------------------------------------------------------------


def test_the_ai_is_sent_the_redacted_description_and_the_cited_tools_only(
    app_parts,  # noqa: F811
) -> None:
    w = _world(app_parts)
    seen: list[dict] = []
    w.use(_provider(True, {"remove": [], "add": [], "unclear": ["[CLIENT] portal"]}, seen))
    r = _parse(w, "drop the Acme portal", "live")
    assert r.status_code == 200, r.text
    (sent,) = seen
    assert {k: v for k, v in sent.items() if not k.startswith("__")} == {
        "description": "drop the [CLIENT] portal",
        "tools": sorted([EDR, SIEM, SOAR], key=str.casefold),
    }
    # Condition 1 holds against the text SENT; condition 2: the quote is shown
    # as sent, placeholder and all.
    assert [(n["text"], n["reason"]) for n in r.json()["not_understood"]] == [
        ("[CLIENT] portal", "ai_unclear")
    ]


# --- records ------------------------------------------------------------------------


def _counts(w) -> dict[str, int]:
    with w.sessions() as db:
        return {
            "llm_calls": db.execute(
                select(func.count())
                .select_from(LLMCall)
                .where(LLMCall.purpose == scenario_intent.PURPOSE)
            ).scalar_one(),
            "audit": db.execute(
                select(func.count())
                .select_from(AuditEntry)
                .where(AuditEntry.action == "attack.scenario.chat_ai_parse")
            ).scalar_one(),
            "scenarios": db.execute(select(func.count()).select_from(AttackScenario)).scalar_one(),
            "runs": db.execute(select(func.count()).select_from(AiRun)).scalar_one(),
        }


@pytest.mark.parametrize(
    ("answer", "fell_back"),
    [(GOOD, False), (RuntimeError("boom"), True), ({"remove": [EDR]}, True)],
    ids=["read", "failed", "refused-by-the-parser"],
)
def test_an_ai_attempt_leaves_one_llm_call_and_one_counts_only_audit_entry(
    app_parts, answer, fell_back  # noqa: F811
) -> None:
    w = _world(app_parts)
    before = _counts(w)
    w.use(_provider(True, answer, []))
    assert _parse(w, VAGUE, "live").status_code == 200
    after = _counts(w)
    assert {k: after[k] - before[k] for k in after} == {
        "llm_calls": 1,
        "audit": 1,
        "scenarios": 0,
        "runs": 0,
    }
    with w.sessions() as db:
        entry = db.execute(
            select(AuditEntry).where(AuditEntry.action == "attack.scenario.chat_ai_parse")
        ).scalar_one()
    details = entry.details
    assert set(details) == {
        "llm_call_id",
        "fell_back",
        "failure",
        "call_row",
        "removed",
        "added",
        "not_understood",
    }
    assert details["fell_back"] is fell_back
    # #863 review, F2: the attempt's own llm_calls row, on a failure too.
    with w.sessions() as db:
        (call_id,) = db.execute(
            select(LLMCall.id).where(LLMCall.purpose == scenario_intent.PURPOSE)
        ).scalars()
    assert details["llm_call_id"] == str(call_id)
    assert details["call_row"] == "found"
    blob = json.dumps(details)
    assert "edr thing" not in blob and EDR not in blob


def test_a_matcher_only_parse_records_nothing(app_parts) -> None:  # noqa: F811
    w = _world(app_parts)
    before = _counts(w)
    w.use(_provider(True, GOOD, []))
    assert _parse(w, VAGUE, "offline").status_code == 200
    assert _counts(w) == before


def test_a_tenant_users_name_in_the_description_reaches_the_ai_redacted(
    app_parts,  # noqa: F811
) -> None:
    """#863 review, F1: the tenant's user names are a name dictionary for the
    redactor (`name_hints_for_tenant`, as Tech Debt's extraction uses it), so a
    colleague named in the description is sent as [NAME], and condition 1 is
    checked against that same text."""
    import uuid

    w = _world(app_parts)
    with w.sessions() as db:
        db.add(
            User(
                email="dana.whitfield@acme.example",
                password_hash="x" * 64,
                role=UserRole.CLIENT,
                display_name="Dana Whitfield",
                client_id=uuid.UUID(w.cid),
            )
        )
        db.commit()
    seen: list[dict] = []
    w.use(
        _provider(True, {"remove": [], "add": [], "unclear": ["the edr thing [NAME] runs"]}, seen)
    )
    r = _parse(w, "drop the edr thing Dana Whitfield runs", "live")
    assert r.status_code == 200, r.text
    (sent,) = seen
    assert "Dana" not in sent["description"] and "Whitfield" not in sent["description"]
    assert "[NAME]" in sent["description"]
    assert r.json()["source"] == "ai"
    assert [(n["text"], n["reason"]) for n in r.json()["not_understood"]] == [
        ("the edr thing [NAME] runs", "ai_unclear")
    ]


def test_an_attempt_whose_call_row_cannot_be_named_says_so_and_keeps_its_cause(
    app_parts, capsys  # noqa: F811
) -> None:
    """#863 review, round 3: never a silent null, and never at the cost of the
    attempt's own outcome. Two parses sent with the SAME X-Request-ID make the
    second one's row ambiguous, for real: its entry says `call_row: unknown`,
    keeps `failure` as the provider's error, and an error is logged."""
    w = _world(app_parts)
    w.use(_provider(True, RuntimeError("boom"), []))
    headers = {**w.h, "X-Request-ID": "the-same-request-id"}
    url = f"/attack/services/{w.svc_id}/scenarios/parse"
    body = {"text": VAGUE, "serves": "live"}
    assert w.c.post(url, headers=headers, json=body).status_code == 200
    capsys.readouterr()
    assert w.c.post(url, headers=headers, json=body).status_code == 200
    logged = capsys.readouterr().out
    with w.sessions() as db:
        entries = list(
            db.execute(
                select(AuditEntry).where(AuditEntry.action == "attack.scenario.chat_ai_parse")
            ).scalars()
        )
    unknown = [e.details for e in entries if e.details["call_row"] == "unknown"]
    assert len(entries) == 2 and len(unknown) == 1
    assert (unknown[0]["llm_call_id"], unknown[0]["failure"]) == (None, "RuntimeError")
    # THIS event's own line, parsed: the provider failure logs an error too,
    # so a level found anywhere in the output would prove nothing.
    events = []
    for line in logged.splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    (event,) = [e for e in events if e.get("event") == "attack.scenario.chat_ai_call_row_unknown"]
    assert (event["level"], event["failure"]) == ("error", "RuntimeError")


def test_two_attempts_each_record_their_own_call(app_parts) -> None:  # noqa: F811
    """The row is found by THIS request's correlation id, so a second attempt
    on the same service, by the same admin, names its own call, not either."""
    w = _world(app_parts)
    w.use(_provider(True, RuntimeError("boom"), []))
    assert _parse(w, VAGUE, "live").status_code == 200
    assert _parse(w, VAGUE, "live").status_code == 200
    with w.sessions() as db:
        calls = set(
            map(
                str,
                db.execute(
                    select(LLMCall.id).where(LLMCall.purpose == scenario_intent.PURPOSE)
                ).scalars(),
            )
        )
        named = [
            e.details["llm_call_id"]
            for e in db.execute(
                select(AuditEntry).where(AuditEntry.action == "attack.scenario.chat_ai_parse")
            ).scalars()
        ]
    assert len(calls) == 2
    assert sorted(named) == sorted(calls)
