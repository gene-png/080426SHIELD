"""RR-1 (for #1122): which services a Risk Register was generated from, chosen
by the admin, and what was left out.

Design note rev 12 (approved, #736 6133670854), §4 and §6.5. A register now
records, beside the `inputs` it drew findings from, a `selection`:

    "selection": {
      "version": 1,
      "included":   [{"kind", "service_id", "framework"}],  # CSF and ZT chosen
      "deselected": [{"kind", "service_id", "framework"}],  # eligible, left out
      "ineligible": [{"kind", "service_id", "framework"}],  # engaged, no record
    }

Only CSF and ZT appear in the three lists: they are the kinds a selection
names. ATT&CK is always included, and Tech Debt is ATT&CK's tool-list
provenance, never a choice.

`selection_of` is the ONE reader of that record, for publish, the Inputs panel,
the response and the files alike. It never raises: anything it cannot use is
`SELECTION_UNREADABLE`, and an absent key is `SELECTION_NOT_RECORDED`. Missing
data defaults to UNCONFIRMED, so both are refused at publish (§5.3).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from app.logging import get_logger

_log = get_logger(__name__)

#: The kinds a selection names. ATT&CK is implicit; Tech Debt is not a choice.
SELECTABLE_KINDS: Final = ("csf", "zt")

#: The stored ZT framework values (`_ZT_FRAMEWORK_BY_SERVICE_KIND`).
ZT_FRAMEWORKS: Final = ("cisa_ztmm_2_0", "dod_ztra")

SELECTION_VERSION: Final = 1


@dataclass(frozen=True)
class SelectionRow:
    kind: str
    service_id: str
    #: The ZT framework; None for CSF.
    framework: str | None

    def as_json(self) -> dict:
        return {"kind": self.kind, "service_id": self.service_id, "framework": self.framework}


@dataclass(frozen=True)
class Selection:
    """A parsed `selection` that passed every consistency check (§4)."""

    included: tuple[SelectionRow, ...]
    deselected: tuple[SelectionRow, ...]
    ineligible: tuple[SelectionRow, ...]

    def as_json(self) -> dict:
        return {
            "version": SELECTION_VERSION,
            "included": [r.as_json() for r in self.included],
            "deselected": [r.as_json() for r in self.deselected],
            "ineligible": [r.as_json() for r in self.ineligible],
        }


@dataclass(frozen=True)
class _Sentinel:
    name: str

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return self.name


#: The provenance has no `selection` key: every register generated before RR-1.
SELECTION_NOT_RECORDED: Final = _Sentinel("SELECTION_NOT_RECORDED")
#: A `selection` is present but cannot be used: not an object (an explicit
#: `null` included), unreadable rows, or a failed consistency check.
SELECTION_UNREADABLE: Final = _Sentinel("SELECTION_UNREADABLE")

SelectionRead = Selection | _Sentinel


def _row(raw: object) -> SelectionRow | None:
    """§4 checks 3 and 4: a readable row, of a selectable kind."""
    if not isinstance(raw, dict):
        return None
    kind = raw.get("kind")
    service_id = raw.get("service_id")
    framework = raw.get("framework")
    if kind not in SELECTABLE_KINDS or not isinstance(service_id, str) or not service_id:
        return None
    if kind == "zt":
        if framework not in ZT_FRAMEWORKS:
            return None
    elif framework is not None:
        return None
    return SelectionRow(kind=kind, service_id=service_id, framework=framework)


def _rows(raw: object) -> tuple[SelectionRow, ...] | None:
    if not isinstance(raw, list):
        return None
    out: list[SelectionRow] = []
    for item in raw:
        row = _row(item)
        if row is None:
            return None
        out.append(row)
    return tuple(out)


def _current_input_ids(raw: object) -> set[str] | None:
    """§4 check 5: `current_inputs` readable, in the shape `publish_blockers`
    reads (a list of objects), each with a string `service_id`."""
    if not isinstance(raw, list):
        return None
    ids: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            return None
        sid = item.get("service_id")
        if not isinstance(sid, str) or not sid:
            return None
        ids.add(sid)
    return ids


def _input_selectable_ids(raw: object) -> set[str] | None:
    """The CSF and ZT service ids in `inputs`, for check 2."""
    if not isinstance(raw, list):
        return None
    ids: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            return None
        if item.get("kind") in SELECTABLE_KINDS:
            sid = item.get("service_id")
            if not isinstance(sid, str) or not sid:
                return None
            ids.add(sid)
    return ids


def _unreadable(why: str) -> _Sentinel:
    _log.warning("risk_selection_unreadable", why=why)
    return SELECTION_UNREADABLE


def selection_of(provenance: object) -> SelectionRead:
    """The register's `selection`, or one of the two sentinels. Never raises.

    The consistency checks run FIRST and in this order: 5, 3, 4, 1, 2 (the
    numbers are the design note's names for them). Each reads only what the
    ones before it proved readable, so none can raise on a malformed record.
    No list wins a conflict: a "skip deselected" rule applied before these
    checks would skip an id that is also an input, and fail open.
    """
    if not isinstance(provenance, dict) or "selection" not in provenance:
        return SELECTION_NOT_RECORDED
    raw = provenance["selection"]
    if not isinstance(raw, dict) or raw.get("version") != SELECTION_VERSION:
        return _unreadable("not a selection object")
    # Check 5: without a readable `current_inputs`, check 1 cannot be judged.
    current_ids = _current_input_ids(provenance.get("current_inputs"))
    if current_ids is None:
        return _unreadable("current_inputs unreadable")
    # Checks 3 and 4: every row readable, every row CSF or ZT.
    lists = [_rows(raw.get(name)) for name in ("included", "deselected", "ineligible")]
    if any(rows is None for rows in lists):
        return _unreadable("a row is unreadable or not CSF/ZT")
    included, deselected, ineligible = (rows or () for rows in lists)
    # Check 1: `current_inputs`, `deselected` and `ineligible` pairwise
    # disjoint by service id (and no id twice inside one list).
    des_ids = [r.service_id for r in deselected]
    inel_ids = [r.service_id for r in ineligible]
    if (
        len(set(des_ids)) != len(des_ids)
        or len(set(inel_ids)) != len(inel_ids)
        or current_ids & set(des_ids)
        or current_ids & set(inel_ids)
        or set(des_ids) & set(inel_ids)
    ):
        return _unreadable("current_inputs, deselected and ineligible overlap")
    # Check 2: `included` equals the CSF and ZT service ids in `inputs`.
    input_ids = _input_selectable_ids(provenance.get("inputs"))
    inc_ids = [r.service_id for r in included]
    if input_ids is None or len(set(inc_ids)) != len(inc_ids) or set(inc_ids) != input_ids:
        return _unreadable("included does not match inputs")
    return Selection(included=included, deselected=deselected, ineligible=ineligible)


def is_recorded(selection: SelectionRead) -> bool:
    return isinstance(selection, Selection)


# ---------------------------------------------------------------------------
# Roles: one per engaged service, for publish AND the Inputs panel (§6.5)
# ---------------------------------------------------------------------------

#: `included`: recorded in `current_inputs` (ATT&CK, CSF, ZT).
#: `provenance-only`: Tech Debt recorded in `current_inputs`.
#: `deselected` / `ineligible`: in that list of the selection.
#: `unrecorded`: ATT&CK or Tech Debt engaged with no record in `current_inputs`.
#: `unnamed`: CSF or ZT in none of the lists (engaged after generate).
ROLES: Final = (
    "included",
    "provenance-only",
    "deselected",
    "ineligible",
    "unrecorded",
    "unnamed",
)


@dataclass(frozen=True)
class Role:
    name: str
    #: The ZT framework of the selection row, when the role came from one.
    framework: str | None = None


def selection_roles(
    selection: Selection,
    recorded_ids: set[tuple[str, str]],
    engaged: list[tuple[str, str]],
) -> dict[tuple[str, str], Role]:
    """Each engaged `(kind, service_id)`'s role in this register.

    Keyed exactly as `publish_blockers` keys, with kind in `INPUT_KINDS`, so
    ZT CISA and DoD are both kind `zt`. Called only with a parsed selection;
    the two sentinels are handled before it. Publish maps each role to its
    blocker and the panel maps it to `in_register`, so the two cannot
    disagree.
    """
    deselected = {r.service_id: r for r in selection.deselected}
    ineligible = {r.service_id: r for r in selection.ineligible}
    roles: dict[tuple[str, str], Role] = {}
    for kind, sid in engaged:
        if (kind, sid) in recorded_ids:
            roles[(kind, sid)] = Role("provenance-only" if kind == "tech_debt" else "included")
        elif sid in deselected:
            roles[(kind, sid)] = Role("deselected", deselected[sid].framework)
        elif sid in ineligible:
            roles[(kind, sid)] = Role("ineligible", ineligible[sid].framework)
        elif kind in ("attack", "tech_debt"):
            roles[(kind, sid)] = Role("unrecorded")
        else:
            roles[(kind, sid)] = Role("unnamed")
    return roles


def zt_service_count(provenance: object, selection: SelectionRead) -> int | None:
    """§6.2's naming predicate's count: the ZT services the register's lines
    mention, across `inputs`, `deselected` and `ineligible`. None when `inputs`
    is unreadable."""
    raw = provenance.get("inputs") if isinstance(provenance, dict) else None
    if not isinstance(raw, list):
        return None
    zt_inputs = sum(1 for i in raw if isinstance(i, dict) and i.get("kind") == "zt")
    if isinstance(selection, Selection):
        zt_inputs += sum(1 for r in selection.deselected if r.kind == "zt")
        zt_inputs += sum(1 for r in selection.ineligible if r.kind == "zt")
    return zt_inputs
