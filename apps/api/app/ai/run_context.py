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
