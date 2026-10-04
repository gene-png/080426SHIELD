"""Which target a Risk Register's findings were measured against (#474).

Every CSF and ZT finding is "current is below target", so the target decides
whether a row exists at all. `generate` records it per service in the
register's provenance (`targets`), and this module is the ONE reader of that
record, used by the admin response, the client dashboard and the exports, so
the three cannot come to disagree about one register.

Shape written by `routes/risk.py::generate`:

    {"csf": {"target": 4, "source": "client", "origin": "live_at_generate"},
     "zt":  {"target": 3, "source": "default", "origin": "live_at_generate"}}

`source` is the resolver's (`resolve_target_tier` / `resolve_target_stage`):
whether the client's choice was used, absent, or unusable. `origin` is WHEN
the target was read; `live_at_generate` is the only value any writer produces
today.

Three states, kept apart: no `targets` key (a register generated before this
was recorded; nothing is known), a readable record, and a record this reader
cannot read, which is reported as not recorded and logged, never as an answer.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.logging import get_logger

_log = get_logger(__name__)

#: The origins a reader can render. Anything else is unreadable.
ORIGINS = ("live_at_generate",)


@dataclass(frozen=True)
class TargetUsed:
    service: str
    target: int
    source: str
    origin: str


def _plain_int(value: object) -> bool:
    # `bool` is an `int` in Python; `CLAUDE.md`: `int()` is not a validator.
    return isinstance(value, int) and not isinstance(value, bool)


def targets_used(stored: object) -> tuple[list[TargetUsed], bool]:
    """`(rows, recorded)` from a register's provenance blob."""
    if not isinstance(stored, dict) or "targets" not in stored:
        return [], False
    raw = stored["targets"]
    rows: list[TargetUsed] = []
    if isinstance(raw, dict) and raw:
        for service, entry in sorted(raw.items()):
            if not (
                isinstance(service, str)
                and isinstance(entry, dict)
                and _plain_int(entry.get("target"))
                and isinstance(entry.get("source"), str)
                and entry.get("origin") in ORIGINS
            ):
                rows = []
                break
            rows.append(
                TargetUsed(
                    service=service,
                    target=entry["target"],
                    source=entry["source"],
                    origin=entry["origin"],
                )
            )
        if rows:
            return rows, True
    _log.error("risk_register_targets_unreadable", got=repr(raw)[:200])
    return [], False
