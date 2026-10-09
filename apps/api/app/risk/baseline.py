"""Which target a Risk Register's findings were measured against (#474).

Every CSF and ZT finding is "current is below target", so the target decides
whether a row exists at all. `generate` records it per service in the
register's provenance (`targets`), and this module is the ONE reader of that
record, used by the admin response, the client dashboard and the exports, so
the three cannot come to disagree about one register.

Shape written by `routes/risk.py::generate` (advisor, #736 6054419744,
approving 6053630989):

    {"csf": {"target": 4, "source": "client", "kind": "csf",
             "framework": None, "origin": "live_at_generate"},
     "zt:cisa_ztmm_2_0": {"target": 4, "source": "client", "kind": "zt",
                          "framework": "cisa_ztmm_2_0", "origin": ...},
     "zt:dod_ztra": {...}}

The dict key is the source's scope key, an id only: it is NEVER parsed and
never rendered. What a line names comes from `kind` and `framework`.

`source` is the resolver's (`resolve_target_tier` / `resolve_target_stage`):
whether the client's choice was used, absent, or unusable. Since #474 D' a CSF
entry is `{"target": None, "source": "playbook"}`: its findings are measured
against each subcategory's Playbook `target_level`, so it names no single
target. Only CSF may carry it, and only with that source. `origin` is WHEN
the target was read; `live_at_generate` is the only value any writer produces
today.

How each stored state reads:

- no `targets` key (a register generated before #474): not recorded;
- an entry with `kind`: `csf` with framework None, or `zt` with a known
  `ZtFramework`;
- a legacy entry without `kind`, under a bare "csf" or "zt" key (written by
  #474 before `kind` was stored): read as that kind, framework None;
- anything else, including a "zt:<...>" key without `kind`, an empty record
  (unreachable: generate requires `has_attack and (has_csf or has_zt)`, and
  every CSF or ZT source gets a target), and two entries of one kind and
  framework: unreadable, logged, and reported as not recorded, never as an
  answer (ruling 2d, fail closed).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.logging import get_logger
from app.models.zt_assessment import ZtFramework

_log = get_logger(__name__)

#: #474 D': a CSF record measured against each subcategory's Playbook
#: `target_level`, so it names no single target.
PLAYBOOK_SOURCE = "playbook"

#: The origins a reader can render. Anything else is unreadable.
ORIGINS = ("live_at_generate",)

#: The kinds a target line can name, each with the frameworks it may carry.
_FRAMEWORKS: dict[str, frozenset[str | None]] = {
    "csf": frozenset({None}),
    "zt": frozenset(f.value for f in ZtFramework),
}


@dataclass(frozen=True)
class TargetUsed:
    kind: str
    framework: str | None
    target: int | None
    source: str
    origin: str


def _plain_int(value: object) -> bool:
    # `bool` is an `int` in Python; `CLAUDE.md`: `int()` is not a validator.
    return isinstance(value, int) and not isinstance(value, bool)


def _row(key: object, entry: object) -> TargetUsed | None:
    """One stored entry, or None when it cannot be read."""
    if not (
        isinstance(key, str)
        and isinstance(entry, dict)
        and (
            _plain_int(entry.get("target"))
            or (entry.get("target") is None and entry.get("source") == PLAYBOOK_SOURCE)
        )
        and isinstance(entry.get("source"), str)
        and entry.get("origin") in ORIGINS
    ):
        return None
    if "kind" in entry:
        kind, framework = entry["kind"], entry.get("framework", "absent")
        # #474 D': only CSF measures per subcategory (the Playbook), and only
        # it may carry no single target.
        if (entry.get("source") == PLAYBOOK_SOURCE) != (
            kind == "csf" and entry.get("target") is None
        ):
            return None
        if not isinstance(kind, str) or not (framework is None or isinstance(framework, str)):
            return None
        if framework not in _FRAMEWORKS.get(kind, frozenset()):
            return None
    elif key in _FRAMEWORKS:
        # Legacy, before `kind` was stored: only a bare kind key, compared
        # whole and never parsed. Its framework was not recorded.
        kind, framework = key, None
    else:
        return None
    return TargetUsed(
        kind=kind,
        framework=framework,
        target=entry["target"],
        source=entry["source"],
        origin=entry["origin"],
    )


def targets_used(stored: object) -> tuple[list[TargetUsed], bool]:
    """`(rows, recorded)` from a register's provenance blob, sorted by
    `(kind, framework)`."""
    if not isinstance(stored, dict) or "targets" not in stored:
        return [], False
    raw = stored["targets"]
    rows: list[TargetUsed] = []
    if isinstance(raw, dict) and raw:
        for key, entry in raw.items():
            row = _row(key, entry)
            if row is None:
                rows = []
                break
            rows.append(row)
        pairs = {(r.kind, r.framework) for r in rows}
        if rows and len(pairs) == len(rows):
            return sorted(rows, key=lambda r: (r.kind, r.framework or "")), True
    _log.error("risk_register_targets_unreadable", got=repr(raw)[:200])
    return [], False
