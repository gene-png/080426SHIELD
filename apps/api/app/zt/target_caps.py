"""The per-capability target disclosures for DoD (#839), in the approved copy.

ONE derivation of the sentences, called by every surface that renders a
`GapAnalysis`: the workspace's gap endpoint, the client's dashboard and the
three deliverables. The copy is the advisor's C1 and C2 (#736, 18:56Z),
verbatim; the web renders the API's sentences and never rebuilds them.
"""

from __future__ import annotations

from app.zt.catalog import capability_by_code
from app.zt.scoring import GapAnalysis


def target_cap_sentences(gap: GapAnalysis) -> list[str]:
    """C1 for each capped capability, then C2 for each capability with no
    Target level, in catalog order."""
    out = []
    for code in gap.capped_target_codes:
        cap = capability_by_code(code)
        out.append(
            f"{cap.dod_number} {cap.name} has no DoD Advanced activities, "
            "so its target is Target (2)."
        )
    for code in gap.no_target_level_codes:
        cap = capability_by_code(code)
        out.append(
            f"{cap.dod_number} {cap.name} has no DoD Target activities, "
            "so it moves from Below Target straight to Advanced."
        )
    return out
