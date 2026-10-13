"""A stand-in api process for the redaction-isolation tests (#552).

Run as `python -m tests._isolation_api_stand_in <pid file> <budget seconds>`
from apps/api. It starts one redaction whose child writes its PID to the file
and spins, and blocks on it. A test then kills THIS process outright (SIGKILL,
as an OOM kill does) and checks the child does not outlive it.
"""

from __future__ import annotations

import os
import sys


def main() -> None:
    pid_file, budget = sys.argv[1], sys.argv[2]
    os.environ["SHIELD_REDACTION_BUDGET_SECONDS"] = budget
    from app.ai import isolation
    from tests import _isolation_targets as targets

    isolation._TARGET = targets.write_pid_then_spin
    isolation.redact_payload_isolated(
        {"__pid_file__": pid_file}, mode="strict", client_org_name=None, name_hints=()
    )


if __name__ == "__main__":
    main()
