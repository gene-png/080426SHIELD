"""`run_batches` cancels queued batches on ANY exception, not only its deadline.

#806 (#952 round 4, F1; the advisor's option (b) on #736): before this,
`app.ai.batching.run_batches` cancelled queued work only when its run deadline
fired (`TimeoutError`). A Ctrl-C, or any other exception raised while the
caller waited for results, left every queued batch in the thread pool, so they
went on to start, and bill, after the caller had stopped listening.

Each test holds the FIRST provider call open, raises an exception where the
caller waits for results (`as_completed`, the line a Ctrl-C interrupts), then
releases the held call and waits for the pool's threads to finish. It counts
the provider calls actually made:

* exactly one -- the call already under way, which nothing can cancel -- and
  none of the queued batches;
* and the exception that reaches the caller is the ORIGINAL one, unchanged
  (the same object), not a wrapped or typed replacement.

The batch count is far above the pool size (one worker), so a queued batch
starting is not a matter of timing.
"""

from __future__ import annotations

import os
import threading
import uuid
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.ai.llm import FixtureProvider, LLMClient, LLMResponse

pytestmark = pytest.mark.unit

#: Far more batches than the pool's one worker can run at once.
BATCHES = 6


@pytest.fixture()
def db(tmp_path) -> Iterator[Session]:
    url = f"sqlite:///{tmp_path / 'batches.db'}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    with sessionmaker(bind=engine, future=True)() as session:
        yield session


class _HeldProvider:
    """A fixture provider whose FIRST call is held open until released, and
    which counts every call it receives from any thread."""

    def __init__(self) -> None:
        self.provider = FixtureProvider()
        self.calls = 0
        self.entered = threading.Event()
        self.release = threading.Event()
        self._lock = threading.Lock()
        self.provider.register("mitre_map", self._respond)

    def _respond(self, _payload: dict) -> LLMResponse:
        with self._lock:
            self.calls += 1
            first = self.calls == 1
        if first:
            self.entered.set()
            assert self.release.wait(10), "the held call was never released"
        # `_MITRE_MAP_PROMPT`'s shape: {"techniques": [...]}.
        return LLMResponse('{"techniques": []}', input_tokens=1, output_tokens=1)


def _run_interrupted(db: Session, monkeypatch, exc: BaseException) -> tuple[_HeldProvider, Any]:
    """Run `BATCHES` batches on one worker; raise `exc` where the caller waits
    for results, once the first call is under way. Returns the provider and
    what `pytest.raises` caught, after the pool's threads have finished."""
    import app.ai.batching as batching
    from app.models._common import utcnow

    held = _HeldProvider()

    def interrupted_wait(futures, timeout=None):
        assert held.entered.wait(10), "precondition: the first batch never started"
        raise exc
        yield  # pragma: no cover - makes this a generator, as `as_completed` is

    monkeypatch.setattr(batching, "as_completed", interrupted_wait)
    before = set(threading.enumerate())
    try:
        with pytest.raises(type(exc)) as caught:
            batching.run_batches(
                db,
                LLMClient(held.provider),
                "mitre_map",
                [{"technique_codes": [f"T{1000 + i}"]} for i in range(BATCHES)],
                requested_by=uuid.uuid4(),
                service_id=uuid.uuid4(),
                client_id=uuid.uuid4(),
                client_org_name=None,
                name_hints=(),
                deadline_at=utcnow() + timedelta(minutes=5),
                max_workers=1,
                deadline_message="deadline",
            )
    finally:
        held.release.set()
    # Wait for the pool's worker to finish whatever it is going to run.
    for t in set(threading.enumerate()) - before:
        if t.name.startswith("ThreadPoolExecutor"):
            t.join(timeout=10)
    return held, caught


def test_an_ordinary_exception_cancels_the_queued_batches(db, monkeypatch) -> None:
    original = RuntimeError("the caller failed while waiting for results")
    held, caught = _run_interrupted(db, monkeypatch, original)
    assert caught.value is original, "the original exception, unchanged"
    assert held.calls == 1, f"queued batches started after the exception: {held.calls} calls"


def test_a_keyboard_interrupt_cancels_the_queued_batches(db, monkeypatch) -> None:
    original = KeyboardInterrupt()
    held, caught = _run_interrupted(db, monkeypatch, original)
    assert caught.value is original, "the original KeyboardInterrupt, unchanged"
    assert held.calls == 1, f"queued batches started after Ctrl-C: {held.calls} calls"
