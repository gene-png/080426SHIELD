"""#797: a batched Run-AI stops at the FIRST credential rejection.

Measured 2026-10-02 on the dev stack: an ATT&CK Run-AI against a rejected key
made all 24 `mitre_map` batch calls, every one a 401. The loop counted each
failure and went on, because a failed batch is ordinarily worth surviving: a
dropped connection costs one batch, not the run. A rejected key is not that.
Every later call is rejected for the same reason, so each one is a provider
round trip and an `llm_calls` row that can only say the same thing.

So `app.ai.batching.run_batches` starts no batch after the first credential
rejection: a bad key costs at most one call per worker -- the ones already in
flight -- instead of one per batch. The bound is pinned to the pool-size
constant each loop is given, with N well above it so it cannot pass by luck,
and a pool of one makes it exactly one call. Everything here is driven through
the run endpoints a consultant reaches, never the helper, and counts the
provider calls actually made.

A credential rejection is narrow and TYPED -- the provider SDK's auth/permission
exception, or an HTTP 401/403 -- never a match on message text. A rate limit, a
5xx, a timeout or a malformed answer still costs one batch and the run goes on,
exactly as before.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable

import anthropic
import httpx
import pytest
from sqlalchemy import select

from app.ai.llm import LLMResponse
from app.models.ai_run import AiRun
from app.models.llm_call import LLMCall
from tests._ai_runs import get_run, start_run
from tests.unit.test_ai_runs_attack import (  # noqa: F401  (fixture)
    LiveLookingProvider,
    _deferred,
    app_parts,
)
from tests.unit.test_csf_run_ai_batched import world  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit

_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_OPENAI_URL = "https://api.openai.com/v1/chat/completions"


def _anthropic(cls: type, status: int) -> Callable[[], Exception]:
    def make() -> Exception:
        resp = httpx.Response(status, request=httpx.Request("POST", _ANTHROPIC_URL))
        return cls("rejected", response=resp, body=None)

    return make


def _http(status: int) -> Callable[[], Exception]:
    """What the OpenAI, Gemini and Vertex adapters raise: `raise_for_status()`."""

    def make() -> Exception:
        req = httpx.Request("POST", _OPENAI_URL)
        resp = httpx.Response(status, request=req)
        return httpx.HTTPStatusError(f"Client error '{status}'", request=req, response=resp)

    return make


REJECTIONS = {
    "anthropic-401": _anthropic(anthropic.AuthenticationError, 401),
    "anthropic-403": _anthropic(anthropic.PermissionDeniedError, 403),
    "http-401": _http(401),
    "http-403": _http(403),
}

#: The message each ends the run with: UNCHANGED by #797, which stops the run
#: sooner and says nothing new. `friendly_reason` words a 401 as a rejected key
#: and a 403 with the generic copy, as it did before.
_KEY_COPY = "The AI provider rejected the configured API key."
_GENERIC_COPY = "The AI call failed and nothing was applied."
MESSAGE = {
    "anthropic-401": _KEY_COPY,
    "anthropic-403": _GENERIC_COPY,
    "http-401": _KEY_COPY,
    "http-403": _GENERIC_COPY,
}

NOT_REJECTIONS = {
    "anthropic-429": _anthropic(anthropic.RateLimitError, 429),
    "anthropic-500": _anthropic(anthropic.InternalServerError, 500),
    "http-429": _http(429),
    "http-503": _http(503),
    # Gemini answers a bad key with 400 API_KEY_INVALID. Stopping on 400 would
    # also stop on a genuine bad request, so it is deliberately NOT a stop.
    "http-400": _http(400),
    "connection": lambda: RuntimeError("provider closed the connection"),
}


class _Calls:
    """Counts provider calls from every batch thread, and raises what it is
    told to on the ones it is told to."""

    def __init__(self, raise_on: Callable[[int], Exception | None]) -> None:
        self.n = 0
        self._lock = threading.Lock()
        self._raise_on = raise_on

    def __call__(self, _payload: dict) -> LLMResponse:
        with self._lock:
            self.n += 1
            i = self.n
        exc = self._raise_on(i)
        if exc is not None:
            raise exc
        return LLMResponse('{"techniques": []}')


def _attack_run(app_parts, calls: _Calls) -> tuple[dict, int]:  # noqa: F811
    """One ATT&CK run, every call going through `calls`. Returns the run and
    how many batches it planned."""
    w, runner = _deferred(app_parts, provider=LiveLookingProvider())
    w.provider.register("mitre_map", calls)
    started = start_run(w.c, w.run_url, w.h, serves="live")
    assert runner.run_all() == 1
    run = get_run(w.c, started["run_id"], w.h)
    with w.sessions() as s:
        rows = s.execute(select(LLMCall)).scalars().all()
        planned = s.get(AiRun, uuid.UUID(started["run_id"])).batches_total
    assert len(rows) == calls.n, "one llm_calls row per provider call"
    assert all(r.ai_run_id == uuid.UUID(started["run_id"]) for r in rows)
    return run, planned


@pytest.mark.parametrize("case", REJECTIONS.keys())
def test_attack_a_rejected_key_costs_at_most_one_call_per_worker(
    app_parts, case  # noqa: F811
) -> None:
    # test-integrity: the bound IS the pool size the loop is given (in-flight calls cannot be recalled); a restated 5 would go stale silently
    from app.routes.attack import _MITRE_MAX_WORKERS

    calls = _Calls(lambda _i: REJECTIONS[case]())
    run, planned = _attack_run(app_parts, calls)

    assert (
        planned is not None and planned > 2 * _MITRE_MAX_WORKERS
    ), f"{planned} batches is too close to the pool of {_MITRE_MAX_WORKERS} to prove a bound"
    assert calls.n <= _MITRE_MAX_WORKERS, f"{calls.n} calls, pool is {_MITRE_MAX_WORKERS}"
    assert calls.n < planned, f"{calls.n} of {planned} batches tried after a rejection"
    assert (run["status"], run["error_reason"]) == ("failed", "ai_call_failed"), run
    # The message is the one it always was: `friendly_reason` of the error.
    assert run["error_message"].startswith(MESSAGE[case]), run["error_message"]
    # Planned vs answered, on the run's existing columns: none of the planned
    # batches answered. Attempted is the llm_calls count, asserted above.
    assert (run["batches_total"], run["batches_failed"]) == (planned, planned), run


def _stopped_line(out: str) -> dict:
    """The `<job>_stopped_on_credential_rejection` log line, parsed."""
    import json

    lines = [
        json.loads(line)
        for line in out.splitlines()
        if line.startswith("{") and "_stopped_on_credential_rejection" in line
    ]
    assert len(lines) == 1, f"expected one stopped line, got {len(lines)}"
    return lines[0]


def test_attack_the_stop_is_logged_with_what_was_attempted_and_planned(
    app_parts, capsys  # noqa: F811
) -> None:
    """Attempted is the provider calls made, never the batches that were
    skipped: a skipped batch is not an attempt."""
    calls = _Calls(lambda _i: REJECTIONS["anthropic-401"]())
    _run, planned = _attack_run(app_parts, calls)

    line = _stopped_line(capsys.readouterr().out)
    assert line["event"] == "mitre_map_stopped_on_credential_rejection"
    assert (line["attempted"], line["planned"], line["answered"]) == (calls.n, planned, 0), line


def test_attack_with_one_worker_a_rejected_key_costs_exactly_one_call(
    app_parts, monkeypatch  # noqa: F811
) -> None:
    """The deterministic form of the bound: with nothing else in flight, the
    first rejection is the only call."""
    import app.routes.attack as attack_routes

    monkeypatch.setattr(attack_routes, "_MITRE_MAX_WORKERS", 1)
    calls = _Calls(lambda _i: REJECTIONS["anthropic-401"]())
    run, planned = _attack_run(app_parts, calls)

    assert calls.n == 1, f"{calls.n} provider calls with one worker"
    assert planned is not None and planned > 1
    assert (run["status"], run["batches_total"], run["batches_failed"]) == (
        "failed",
        planned,
        planned,
    ), run


@pytest.mark.parametrize("make", NOT_REJECTIONS.values(), ids=NOT_REJECTIONS.keys())
def test_attack_any_other_failure_still_tries_every_batch(app_parts, make) -> None:  # noqa: F811
    """The positive control. A guard that stopped on every failure would pass
    the test above and lose a whole run to one dropped connection."""
    calls = _Calls(lambda _i: make())
    run, planned = _attack_run(app_parts, calls)

    assert planned is not None and planned > 1
    assert calls.n == planned, f"{calls.n} of {planned} batches tried"
    assert (run["status"], run["error_reason"]) == ("failed", "ai_call_failed"), run


def test_csf_a_rejected_key_costs_at_most_one_call_per_worker(world) -> None:  # noqa: F811
    """The shared loop's other caller, through CSF's own endpoint: 33 batches."""
    # test-integrity: the bound IS the pool size the loop is given (in-flight calls cannot be recalled); a restated 5 would go stale silently
    from app.routes.csf import _CSF_MAX_WORKERS

    calls = _Calls(lambda _i: REJECTIONS["anthropic-401"]())
    world.provider.register("csf_score", calls)

    started = start_run(world.c, f"/csf/services/{world.svc_id}/run-ai", world.h)
    run = get_run(world.c, started["run_id"], world.h)

    assert calls.n <= _CSF_MAX_WORKERS < 33, f"{calls.n} calls, pool is {_CSF_MAX_WORKERS}"
    assert (run["status"], run["error_reason"]) == ("failed", "ai_call_failed"), run
    assert (run["batches_total"], run["batches_failed"]) == (33, 33), run


def test_csf_a_key_revoked_mid_run_starts_no_further_batches(world) -> None:  # noqa: F811
    """The first batch answers; every call after it is rejected. Batches
    already inside a provider call cannot be recalled, so the bound is the
    pool, not one: but no batch starts after the first rejection, the run
    keeps the answer it paid for, and says how many batches came back empty."""
    # test-integrity: the bound IS the pool size (in-flight calls cannot be recalled); a restated 5 would go stale silently
    from app.routes.csf import _CSF_MAX_WORKERS

    def respond(i: int) -> Exception | None:
        return None if i == 1 else REJECTIONS["anthropic-401"]()

    rec = _Calls(respond)

    def answer(payload: dict) -> LLMResponse:
        rec(payload)
        from tests.unit.test_csf_run_ai_batched import _answer_as_the_prompt_asks

        return _answer_as_the_prompt_asks(payload)

    world.provider.register("csf_score", answer)
    started = start_run(world.c, f"/csf/services/{world.svc_id}/run-ai", world.h)
    run = get_run(world.c, started["run_id"], world.h)

    # The one success, plus at most one call per worker already in flight.
    assert 1 < rec.n <= 1 + _CSF_MAX_WORKERS, f"{rec.n} of 33 batches attempted"
    assert run["status"] == "completed", run
    assert (run["batches_total"], run["batches_failed"]) == (33, 32), run


def test_attack_the_run_names_the_rejection_even_after_another_failure(
    app_parts, monkeypatch  # noqa: F811
) -> None:
    """One worker, so the order is fixed: a 500 on the first call, then the
    rejection. Nothing answered, so the run fails -- and says the KEY was
    rejected, the error that stopped it, not the 500 that happened first."""
    import app.routes.attack as attack_routes

    monkeypatch.setattr(attack_routes, "_MITRE_MAX_WORKERS", 1)

    def respond(i: int) -> Exception:
        return (NOT_REJECTIONS["anthropic-500"] if i == 1 else REJECTIONS["anthropic-401"])()

    calls = _Calls(respond)
    run, _planned = _attack_run(app_parts, calls)

    assert calls.n == 2, f"{calls.n} calls: the 500, then the rejection, then nothing"
    assert run["error_message"].startswith(MESSAGE["anthropic-401"]), run["error_message"]
