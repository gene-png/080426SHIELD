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

The advisor's (ii), in the DRAFTS branch only (#736 6116519635): a draft
row joins the basis only if it was in security scope AT THE BASE
(`in_scope_at`), rebuilt from its classification and the times of its first
confirmation and first override. The scope judged is the BASIS row's, never
the offered row's, which may be a re-extracted copy on another version with
a different history. A tool in the recorded membership of the APPROVED
version in force at the base was offered to the base as frozen at approval,
whatever happened to its classification afterwards.

Limits, stated rather than hidden:

* a draft row's scope at the base is rebuilt from the audit trail, so a
  confirmation or override written without its audit row is invisible. A
  row confirmed out of scope NOW with no confirmation on record reads
  "cannot be checked"; one confirmed and then overridden, both unaudited,
  reads as in scope at the base. The earlier overcount from an override on a
  row ALREADY in scope (a provisional negative, or re-picking an in-scope
  row's functions) is gone: such a row was in scope at the base;
* a RENAME after the base is missed when the old name reached the basis,
  and reads as added when it did not;
* R4 (b) is applied at the base's moment by the snapshot naming a tool, and
  for a draft by its rows created by then being in scope now.
"""

from __future__ import annotations

from collections.abc import Iterable
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
    """A live row of a list version: its name, when it was created, its
    current classification, and from the audit trail when it was FIRST
    confirmed out of scope and FIRST overridden into scope, if ever."""

    name: str
    created_at: datetime
    security_related: bool | None
    confirmed: bool
    first_confirmed_at: datetime | None
    first_overridden_at: datetime | None


def in_scope_at(row: DraftRow, at: datetime) -> bool:
    """Was this row in ATT&CK security scope at `at`? Raises `_Unknown` when
    the record cannot say.

    From the writers: every row starts IN scope (an unconfirmed negative is
    provisional); the confirm route takes a negative OUT and is the only
    thing that does; the override route puts a row back IN for good (it
    clears the confirmation, and the confirm route then refuses the row).
    So a row was in scope at `at` iff its first override was by then, or no
    confirmation was. A row confirmed out of scope with no confirmation on
    record cannot be placed in time."""
    if row.first_overridden_at is not None and _aware(row.first_overridden_at) <= at:
        return True
    if row.first_confirmed_at is not None:
        return _aware(row.first_confirmed_at) > at
    if row.security_related is False and row.confirmed:
        raise _Unknown(f"row {row.name!r}: confirmed out of scope with no record of when")
    return True


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
#:
#: A RATCHET, not a live case. It guards a trail in which `approved_at`, the
#: LAST approval, is older than every audited approval. No current writer
#: produces that: `approve_capability_list` stamps `approved_at` and writes
#: the audit row together, so `approved_at` is never earlier than the last
#: audited approval. It becomes reachable if a writer ever audits an
#: approval without stamping `approved_at` (a restore or an import), or
#: stamps `approved_at` from elsewhere (a backfill); the trail then
#: contradicts itself, and the first approval time is not on record.
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
            # first audited one: the trail contradicts itself (see
            # `_SAME_APPROVAL`), so its first approval is not read from it.
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


def _service_basis(versions: list[ListVersion], at: datetime) -> set[str]:
    newest_first = sorted(versions, key=lambda v: v.version, reverse=True)
    any_approved = False
    for v in newest_first:
        if not _approved_by(v, at):
            continue
        any_approved = True
        names = _membership_at(v, at)
        if names:
            return names
    if any_approved:
        return set()  # R6b: drafts are ignored beside an approved version
    # No version was approved by then, so every version here was a DRAFT at
    # `at`, including one approved only later: that draft was in force then.
    for v in newest_first:
        if not _live_at(v, at):
            continue
        names = {
            name_key(r.name) for r in v.rows if _aware(r.created_at) <= at and in_scope_at(r, at)
        } - {""}
        if names:
            return names
    return set()


def basis_at(base_approved_at: datetime, versions: Iterable[ListVersion]) -> set[str] | None:
    """The tool names the base was offered, by `name_key`; None when the
    record cannot say."""
    at = _aware(base_approved_at)
    by_service: dict[Any, list[ListVersion]] = {}
    for v in versions:
        by_service.setdefault(v.service_id, []).append(v)
    names: set[str] = set()
    try:
        for service_versions in by_service.values():
            names |= _service_basis(service_versions, at)
    except _Unknown:
        return None
    return names


def tools_added(
    offered: Iterable[Any],
    versions: Iterable[ListVersion],
    base_cited: Iterable[str],
    base_approved_at: datetime | None,
) -> list[str] | None:
    """The offered tools (`CapabilityProvenance`s) new since the base, by
    name, sorted case-insensitively; or None when that cannot be checked."""
    if base_approved_at is None:
        return None
    at = _aware(base_approved_at)
    basis = basis_at(at, versions)
    if basis is None:
        return None
    had = basis | {name_key(t) for t in base_cited}
    added = [p.capability.name for p in offered if name_key(p.capability.name) not in had]
    return sorted(added, key=str.casefold)
