"""Which offered tools are new since an ATT&CK base was approved (#1012).

The advisor's option A (#736 6115773247): judge "added since the base" by
tool NAME against what the base was offered, rebuilt from the record. Nothing
stores the offered set itself, so it is rebuilt per Tech Debt service as the
list version IN FORCE at the base's approval, by the R6b rule
(`routes/attack.py::_current_list_versions`) applied at that moment:

* if any version had been APPROVED by then, the newest such version whose
  recorded membership (`approved_membership`, frozen at approval) names a
  tool; its drafts are ignored;
* otherwise the newest version that existed then and had not been
  discarded -- a draft at that moment, even if approved since -- read as its
  rows created by then and in security scope now.

Plus the tools the base itself cites: it credited them, so they are not new
to it.

The answer is None -- "cannot be checked", never a guess -- whenever a step
that could decide it is not on record:

* the base has no approval time;
* a version that could have been the one in force has no readable approval
  time (an APPROVED list with neither an approval audit row nor
  `approved_at`), or was discarded with no record of when;
* the version in force at the base was approved before migration 0043 (no
  recorded membership), or was approved AGAIN after the base, which
  overwrote the membership the base was offered;
* an offered tool names no capability item, so an override cannot be read.

A tool also counts as added when its security classification was overridden
after the base (the advisor's (ii)), but ONLY where the base's basis for it
came from the DRAFTS branch (#736 6116519635): there a draft row is read by
its scope NOW, so an old row an override brought into scope since would
otherwise read as one the base had. A tool in the recorded membership of the
APPROVED version in force at the base was offered to the base, as frozen at
approval, whatever happened to its classification afterwards.

Limits, stated rather than hidden:

* a draft row's security scope is read as it is NOW; a row reclassified out
  of scope since is not offered now either, so it cannot be misjudged as
  added, but one reclassified INTO scope without an override is read as the
  base having had it;
* a RENAME after the base is missed when the old name reached the basis,
  and reads as added when it did not;
* R4 (b) is applied at the base's moment by the snapshot naming a tool, and
  for a draft by its rows created by then being in scope now.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.models.capability import CapabilityListStatus

_APPROVED_STATUSES = frozenset({CapabilityListStatus.APPROVED, CapabilityListStatus.RELEASED})


def name_key(name: object) -> str:
    """The comparison key: the one the what-if's collision check uses
    (`attack/scenario.py::_key`), so two spellings it treats as one tool are
    one tool here too."""
    return str(name or "").strip().casefold()


def _aware(at: datetime) -> datetime:
    """SQLite returns naive datetimes; every time here is UTC."""
    return at if at.tzinfo is not None else at.replace(tzinfo=UTC)


@dataclass(frozen=True)
class DraftRow:
    """A live row of a list version: its name, when it was created, and
    whether it is in security scope now."""

    name: str
    created_at: datetime
    in_scope: bool


@dataclass(frozen=True)
class ListVersion:
    """One Tech Debt list version, with what the record says about its past."""

    service_id: Any
    version: int
    status: CapabilityListStatus
    created_at: datetime
    #: The LAST approval (the approve route stamps it on every approval).
    approved_at: datetime | None
    #: Every `capability_list.approved` audit time for this version.
    approvals: tuple[datetime, ...]
    #: The `capability_list.discarded` audit time, if any.
    discarded_at: datetime | None
    approved_membership: list | None
    rows: tuple[DraftRow, ...]


#: The approve route stamps `approved_at` and writes its audit row in ONE
#: transaction, a few milliseconds apart (`approved_at` first). A gap wider
#: than this is two different approvals, not one.
_SAME_APPROVAL = timedelta(minutes=1)


class _Unknown(Exception):
    """A step that could decide the basis is not on record."""


def _approved_by(v: ListVersion, at: datetime) -> bool:
    """Was this version approved by `at`? Raises `_Unknown` when the record
    cannot say. Only an APPROVED or RELEASED version was ever approved: a
    DRAFT never was, and only a draft can be discarded."""
    if v.status not in _APPROVED_STATUSES:
        return False
    if v.approvals:
        first = min(_aware(t) for t in v.approvals)
        if v.approved_at is not None and _aware(v.approved_at) < first - _SAME_APPROVAL:
            # `approved_at` is the LAST approval, so it cannot precede the
            # first audited one: an approval is missing from the trail, and
            # the first approval may be the missing one.
            raise _Unknown(f"version {v.version}: approval trail is incomplete")
        return first <= at
    if v.approved_at is not None and _aware(v.approved_at) <= at:
        return True  # the last approval was by then, so the first was too
    raise _Unknown(f"version {v.version}: no record of when it was first approved")


def _membership_at(v: ListVersion, at: datetime) -> set[str]:
    """The names this approved version offered at `at`, from its recorded
    membership. Raises `_Unknown` when it was never recorded (pre-0043) or
    was overwritten by an approval after `at`."""
    if v.approved_membership is None:
        raise _Unknown(f"version {v.version}: approved before its membership was recorded")
    last = [_aware(t) for t in v.approvals]
    if v.approved_at is not None:
        last.append(_aware(v.approved_at))
    if any(t > at for t in last):
        raise _Unknown(f"version {v.version}: approved again after the base")
    return {name_key(e.get("name")) for e in v.approved_membership} - {""}


def _live_at(v: ListVersion, at: datetime) -> bool:
    """Did this draft exist, undiscarded, at `at`?"""
    if _aware(v.created_at) > at:
        return False
    if v.status == CapabilityListStatus.DISCARDED:
        if v.discarded_at is None:
            raise _Unknown(f"version {v.version}: discarded with no record of when")
        return _aware(v.discarded_at) > at
    return True


@dataclass(frozen=True)
class Basis:
    """What the base was offered: every name, and the names read from an
    APPROVED version's recorded membership (frozen at approval)."""

    names: frozenset[str]
    from_snapshot: frozenset[str]


def _service_basis(versions: list[ListVersion], at: datetime) -> tuple[set[str], bool]:
    """(names, whether they came from an approved version's snapshot)."""
    newest_first = sorted(versions, key=lambda v: v.version, reverse=True)
    any_approved = False
    for v in newest_first:
        if not _approved_by(v, at):
            continue
        any_approved = True
        names = _membership_at(v, at)
        if names:
            return names, True
    if any_approved:
        return set(), True  # R6b: drafts are ignored beside an approved version
    # No version was approved by then, so every version here was a DRAFT at
    # `at`, including one approved only later: that draft was in force then.
    for v in newest_first:
        if not _live_at(v, at):
            continue
        names = {name_key(r.name) for r in v.rows if r.in_scope and _aware(r.created_at) <= at} - {
            ""
        }
        if names:
            return names, False
    return set(), False


def basis_at(base_approved_at: datetime, versions: Iterable[ListVersion]) -> Basis | None:
    """The tool names the base was offered, by `name_key`; None when the
    record cannot say."""
    at = _aware(base_approved_at)
    by_service: dict[Any, list[ListVersion]] = {}
    for v in versions:
        by_service.setdefault(v.service_id, []).append(v)
    names: set[str] = set()
    from_snapshot: set[str] = set()
    try:
        for service_versions in by_service.values():
            service_names, snapshot = _service_basis(service_versions, at)
            names |= service_names
            if snapshot:
                from_snapshot |= service_names
    except _Unknown:
        return None
    return Basis(frozenset(names), frozenset(from_snapshot))


def tools_added(
    offered: Iterable[Any],
    versions: Iterable[ListVersion],
    base_cited: Iterable[str],
    base_approved_at: datetime | None,
    overridden_at: Mapping[str, datetime] | None = None,
) -> list[str] | None:
    """The offered tools (`CapabilityProvenance`s) new since the base, by
    name, sorted case-insensitively; or None when that cannot be checked."""
    if base_approved_at is None:
        return None
    at = _aware(base_approved_at)
    basis = basis_at(at, versions)
    if basis is None:
        return None
    had = basis.names | {name_key(t) for t in base_cited}
    overrides = overridden_at or {}
    added: list[str] = []
    for p in offered:
        if not p.item_id:
            return None
        key = name_key(p.capability.name)
        override = overrides.get(p.item_id)
        # (ii) only outside an approved snapshot (#736 6116519635).
        late_override = (
            override is not None and _aware(override) > at and key not in basis.from_snapshot
        )
        if key not in had or late_override:
            added.append(p.capability.name)
    return sorted(added, key=str.casefold)
