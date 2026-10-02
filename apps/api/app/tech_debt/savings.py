"""Estimated annual savings: the ONE derivation every Tech Debt surface calls.

The deliverable (`exporters.build_context`), the admin consolidation-plan card
(`routes/tech_debt.consolidation_plan_summary`), the client dashboard and the
home value card (`routes/clients`) each carried their own copy of this loop
until #804, and the savings what-if needs the same figure for dispositions
nobody has saved yet. Four copies of "which dispositions count" is four places
for one decision to land half-made, so it lives here and they call it.

Code computes; nothing here reads an AI output.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from app.models.capability import CapabilityDisposition

#: The dispositions whose annual cost is counted as savings.
SAVINGS_DISPOSITIONS: frozenset[CapabilityDisposition] = frozenset({CapabilityDisposition.CUT})


@dataclass(frozen=True)
class Savings:
    """`amount` is the sum of the costs that are known. `known` is False when
    a counted row has no cost, which makes `amount` a LOWER BOUND, and every
    surface says so ("≥ $…")."""

    amount: float
    known: bool


def estimated_savings(
    rows: Iterable[tuple[CapabilityDisposition | None, float | Decimal | None]],
) -> Savings:
    """`rows` is (disposition, annual cost) per capability."""
    amount = 0.0
    known = True
    for disposition, cost in rows:
        if disposition not in SAVINGS_DISPOSITIONS:
            continue
        if cost is None:
            known = False
        else:
            amount += float(cost)
    return Savings(amount=amount, known=known)
