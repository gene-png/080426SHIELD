"""The Run-AI a provider call belongs to (#645).

A context variable rather than a parameter, for the same reason as
`correlation_id_var`: the call is made several layers below the job that knows
the run, and ATT&CK's batched runner reaches it from pool threads that each run
in a COPY of the job's context. A parameter would have to be threaded through
`run_job` and every runner; this travels with the context the runners already
copy, so a batch cannot lose it the way batches once lost the correlation id.

Its own module so `app/ai/llm.py` can read it without importing the run
framework, which imports `llm.py`.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

ai_run_id_var: ContextVar[uuid.UUID | None] = ContextVar("ai_run_id", default=None)


class InvokeMark:
    """Whether a Run-AI's job has entered `LLMClient.invoke` (#1219).

    Every provider call a Run-AI job makes goes through `invoke`, so a job
    that never entered it sent nothing. (The key check in `keystore.py` calls
    its provider directly, outside any run.) One object per run, set by the run
    framework; the batch pools run in COPIES of the job's context, which share
    this same object, so a batch that calls sets the run's mark. A thread
    started WITHOUT copying the context would lose it -- and `ai_run_id_var`
    with it, which is why every pool here copies.
    """

    def __init__(self) -> None:
        self.entered = False


invoke_mark_var: ContextVar[InvokeMark | None] = ContextVar("invoke_mark", default=None)


def note_invoke_entered() -> None:
    """Called first thing in `LLMClient.invoke`, and by a batch worker before
    its stop check (`batching._one`). Outside a Run-AI, a no-op."""
    mark = invoke_mark_var.get()
    if mark is not None:
        mark.entered = True
