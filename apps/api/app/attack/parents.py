"""A parent technique's status is computed from its sub-techniques (#554, D-094).

The owner's decision on #554: a parent's status is arithmetic over its children;
AI suggests, code computes; `parent_rollup` is forbidden as a reason. So for a
parent that HAS sub-techniques, no consultant or model sets its status: this
function does, and the write paths store its answer.

THE RULE (D-094, my call, overturnable), in precedence order:

1. Any child UNSCORED -> the parent is unscored. Unknown is never rounded up.
2. Any child UNABLE_TO_DETERMINE -> the parent is too. Unverified cannot be
   counted as any assessed value.
3. Set aside children that do not bear on defence here: NOT_APPLICABLE (the
   platform is absent) and OUTSIDE_CONTROL_SURFACE. Of the rest:
   * all covered -> covered; all gap -> gap;
   * anything else (any partial, or a mix) -> partial. Something defends part
     of the technique and not all of it.
4. Nothing left after step 3 -> OUTSIDE_CONTROL_SURFACE if any child is outside
   the surface (the technique applies, just not reachably), else NOT_APPLICABLE.

REASONS. Computed from the children, never invented:
  * N/A parent -> `platform_absent`, the only N/A reason;
  * outside parent -> the children's sub-case when they all share one, else None;
  * every other parent -> None. A computed Partial has no single missing part to
    name: its children carry their own reasons, and they are the evidence. The
    release-readiness gate must read a computed parent's children, not demand a
    Partial reason of the parent (recorded on #554 for that slice).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, NamedTuple

from app.attack.catalog import parent_techniques, sub_techniques
from app.attack.coverage import CoverageStatus

if TYPE_CHECKING:
    from app.models.attack_assessment import AttackCoverage

#: Every parent that HAS sub-techniques, and its children's codes. Derived from
#: the catalog once, so the set of computed parents cannot drift from it.
PARENT_CHILDREN: dict[str, tuple[str, ...]] = {
    p.id: tuple(s.id for s in sub_techniques(p.id))
    for p in parent_techniques()
    if sub_techniques(p.id)
}


def is_computed_parent(code: str) -> bool:
    return code in PARENT_CHILDREN


_SET_ASIDE = {
    CoverageStatus.NOT_APPLICABLE.value,
    CoverageStatus.OUTSIDE_CONTROL_SURFACE.value,
}


def computed_parent_status(
    children: Sequence[tuple[str | None, str | None]],
) -> tuple[str | None, str | None]:
    """`(status, reason_code)` for a parent, from its children's `(status, reason)`."""
    if not children:
        raise ValueError("a parent with no sub-techniques is scored directly, not computed")
    statuses = [status for status, _ in children]
    if any(s is None for s in statuses):
        return None, None
    if CoverageStatus.UNABLE_TO_DETERMINE.value in statuses:
        return CoverageStatus.UNABLE_TO_DETERMINE.value, None
    assessed = [s for s in statuses if s not in _SET_ASIDE]
    if assessed:
        if all(s == CoverageStatus.COVERED.value for s in assessed):
            return CoverageStatus.COVERED.value, None
        if all(s == CoverageStatus.GAP.value for s in assessed):
            return CoverageStatus.GAP.value, None
        return CoverageStatus.PARTIAL.value, None
    outside = [r for s, r in children if s == CoverageStatus.OUTSIDE_CONTROL_SURFACE.value]
    if outside:
        subcases = set(outside)
        shared = subcases.pop() if len(subcases) == 1 else None
        return CoverageStatus.OUTSIDE_CONTROL_SURFACE.value, shared
    return CoverageStatus.NOT_APPLICABLE.value, "platform_absent"


class RecomputeResult(NamedTuple):
    """What a recompute changed: the parents whose status or reason moved, and
    the parents whose legacy lock it removed. Both are audited by the caller."""

    changed: list[str]
    unlocked: list[str]


def recompute_parents(
    rows: Mapping[str, AttackCoverage], parent_codes: Iterable[str] | None = None
) -> RecomputeResult:
    """Write each computed parent's status and reason from its children's rows.

    `rows` is one assessment's coverage rows by technique code. A child with no
    row counts as unscored -- missing data is never rounded up.

    A LOCKED parent is unlocked here, not skipped (#620 review, D-094). A lock
    says "protect this answer from the AI", and a computed parent has no answer
    of its own to protect: skipping it would freeze a number the rule owns, and
    `diff_keyed_rows` hides locked rows, so the freeze would be invisible. The
    PATCH refuses a new lock on a parent; this removes any that predates D-094.
    """
    changed: list[str] = []
    unlocked: list[str] = []
    for code in PARENT_CHILDREN if parent_codes is None else parent_codes:
        parent = rows.get(code)
        if parent is None or code not in PARENT_CHILDREN:
            continue
        if parent.locked:
            parent.locked = False
            unlocked.append(code)
        children = [
            (rows[c].status, rows[c].reason_code) if c in rows else (None, None)
            for c in PARENT_CHILDREN[code]
        ]
        status, reason = computed_parent_status(children)
        if (parent.status, parent.reason_code) != (status, reason):
            parent.status, parent.reason_code = status, reason
            changed.append(code)
    return RecomputeResult(changed, unlocked)
