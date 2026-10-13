"""How long an AI run may live, in a module that imports nothing from `app`.

Moved here from `app/ai/runs.py` (#552) so `app/config.py` can bound the
redaction budget and slot wait by the run's own deadline without importing the
run framework (which imports `app.ai.isolation`, which imports `app.config`).
`runs.py` imports both names, so `runs.RUN_DEADLINE` is still the run's
deadline everywhere it is read.
"""

from __future__ import annotations

from datetime import timedelta

#: How long a run may hold its service's edit lock. Sized above the longest
#: measured run: ATT&CK's 26 batches at 5 workers, ~30s of generation each
#: (`routes/attack.py`, `_MITRE_BATCH_SIZE`), is ~3 minutes when healthy, and a
#: rate-limited provider has been seen to stretch a single batch to minutes.
RUN_DEADLINE = timedelta(minutes=45)

#: How far past its deadline a run THIS process is still executing may go
#: before a status read ends it. The ATT&CK job checks its own deadline between
#: batches; this margin is for a job blocked inside one provider call, which
#: cannot check anything until the call returns.
REAP_MARGIN = timedelta(minutes=5)
