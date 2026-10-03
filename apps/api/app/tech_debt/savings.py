"""Estimated annual savings: the ONE derivation every Tech Debt surface calls.

Five surfaces each carried their own copy of this loop until #804: the
deliverable (`exporters.build_context`), the admin consolidation-plan card
(`routes/tech_debt.consolidation_plan_summary`), and in `routes/clients` the
client dashboard's headline, its per-category redundancy savings and the home
value card. And
the savings what-if needs the same figure for dispositions nobody has saved
yet. Five copies of "which dispositions count" is five places for one decision
to land half-made, so it lives here and they call it.

Code computes; nothing here reads an AI output.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from app.models.capability import RETIRING_DISPOSITIONS, CapabilityDisposition

#: The dispositions whose annual cost is counted as savings: the RETIRING ones,
#: "Cut" and "Cut, covered by another tool" (stored `consolidate`), each at the
#: tool's FULL annual cost. The SAME definition ATT&CK's planned-retirement
#: marks read (`models/capability.py::RETIRING_DISPOSITIONS`), so savings and
#: retirement cannot disagree. Ruled by the advisor on #736, 2026-10-02/03
#: (#804, #810). Keep and Undecided count nothing.
SAVINGS_DISPOSITIONS: frozenset[CapabilityDisposition] = RETIRING_DISPOSITIONS


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
