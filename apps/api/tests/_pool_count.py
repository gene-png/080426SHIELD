"""Counting pooled connections while a provider is being called (#1025).

`pool_count()` counts connections checked out of ANY pool since entry; CI runs
SQLite, so it is the SQLAlchemy pool that is counted, which is what ran out on
#1025. `sampling_provider_calls` records that count at every provider call, by
wrapping `FixtureProvider.complete` (live-looking test providers subclass it).
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import event
from sqlalchemy.pool import Pool


@contextmanager
def pool_count() -> Iterator[list[int]]:
    """Connections checked out since entry, live, as `[n]`."""
    held = [0]
    lock = threading.Lock()

    def _out(*_a) -> None:
        with lock:
            held[0] += 1

    def _in(*_a) -> None:
        with lock:
            held[0] -= 1

    event.listen(Pool, "checkout", _out)
    event.listen(Pool, "checkin", _in)
    try:
        yield held
    finally:
        event.remove(Pool, "checkout", _out)
        event.remove(Pool, "checkin", _in)


@contextmanager
def sampling_provider_calls(monkeypatch) -> Iterator[list[int]]:
    """The pool count at every provider call made inside the block."""
    from app.ai import llm as llm_module

    samples: list[int] = []
    real = llm_module.FixtureProvider.complete
    with pool_count() as held:

        def complete(self, prompt, payload):
            samples.append(held[0])
            return real(self, prompt, payload)

        monkeypatch.setattr(llm_module.FixtureProvider, "complete", complete)
        yield samples
