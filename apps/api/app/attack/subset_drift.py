"""ATT&CK rows that credit a tool outside the client's CURRENT security subset (#851).

A row stores tool NAMES. They are checked against the client's security tool
list only when Run AI writes them, and a re-run skips a locked row and one a
consultant edited mid-run; a consultant's PATCH stores names as typed. So a
row can go on crediting a tool after the client's list stops offering it, and
R3 (`attack/computed.py::capability`) counts it as in place.

The ruling (advisor, #736 comment 5984022081): DISCLOSE it on the workspace,
refuse approve while a draft has any, and disclose after approval. R3 itself
is not changed here (option B, filed as #888).

**"The same tool" is decided by the run's own resolver, never by a second
comparison.** The resolver here is built exactly as Run AI builds its own
(`routes/attack.py::citation_resolver_for`), and a name is in the subset when
the resolver's NAME tiers know it (`CitationResolver.named_by`: the stored
name, case and whitespace, or the form the AI is shown). An inference -- a
vendor, a substring -- does not count: a tool that left the subset must not be
read as a sibling product that stayed.

`attack/retirement.py` joins names to plan entries by `strip().casefold()`.
It answers a different question (WHICH entry's disposition applies); the two
can disagree on a vendor-shaped name, and that is stated there too.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.attack.citations import CitationResolver
from app.attack.pending import TOOL_FIELDS


@dataclass(frozen=True)
class OutsideCitation:
    """One tool one row credits outside the subset. `locked`: Run AI will not
    change this row, so the remedy is to remove the tool by hand."""

    technique_code: str
    field: str
    tool: str
    locked: bool


def is_outside_subset(name: str, subset: CitationResolver) -> bool:
    """THE ONE PREDICATE for "outside the subset" (D1 on #851, recommended and
    pending the advisor): any cited name the subset's name tiers do not know,
    whether it LEFT the subset (a confirmed "not security" or "not in use"
    sign-off, or a list approved again without it) or was typed by hand and
    was never on the list.

    The narrower reading (D1(b): only a name the client's list still holds,
    kept out of the subset) would add one condition here: that the name hits
    a resolver over `CapabilityMembership.withheld`. Nothing else changes."""
    return not subset.named_by(name)


def citations_outside_subset(
    rows: Iterable[Any], subset: CitationResolver
) -> list[OutsideCitation]:
    """Every (row, field, tool) credited outside the subset, by technique code
    then field, locked or not: an unlocked row credits the tool too, until a
    re-run, and `locked` says which a re-run will NOT fix."""
    out: list[OutsideCitation] = []
    for row in sorted(rows, key=lambda r: r.technique_code):
        for field in TOOL_FIELDS:
            for tool in getattr(row, field, None) or []:
                if isinstance(tool, str) and tool.strip() and is_outside_subset(tool, subset):
                    out.append(
                        OutsideCitation(
                            technique_code=row.technique_code,
                            field=field,
                            tool=tool,
                            locked=bool(row.locked),
                        )
                    )
    return out
