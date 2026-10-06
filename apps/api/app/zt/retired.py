"""Answers recorded against a row the ZT catalog no longer has (#838).

#838 corrected the CISA catalog to CISA ZTMM 2.0, and migration 0063 KEPT the
answers on the 13 rows CISA does not have (decision 4, option B) rather than
delete them. The ZT scoring and gap engines iterate the catalog, and Risk
synthesis filters to its codes (`routes/risk.py`), so those rows are not scored.
This module is the ONE derivation of how many of them hold an answer, and of
the sentence that discloses it, for the workspace (`routes/zt.py`) and the
three exporters (`zt/exporters.py`) alike. It is derived from the catalog and
the stored rows on every read, so it agrees with the engines that iterate the
catalog; a reader that reads stored rows directly must filter to the catalog's
codes itself, as `routes/risk.py` does.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.zt.catalog import all_codes
from app.zt.maturity import ZtFrameworkCode

#: The document each framework's catalog is taken from, as the approved
#: disclosure names it (#838 comment 5982917066, decision 4).
_SOURCE = {
    ZtFrameworkCode.CISA_ZTMM_2_0: "CISA ZTMM 2.0",
    ZtFrameworkCode.DOD_ZTRA: "the DoD Zero Trust Capability Execution Roadmap",
}


def has_recorded_answer(answer: Any) -> bool:
    """A stage, a target, notes with text, or evidence: anything someone
    recorded. An empty row is not an answer."""
    return (
        answer.maturity_stage is not None
        or answer.target_stage is not None
        or bool((answer.notes or "").strip())
        or answer.evidence_artifact_id is not None
    )


def retired_answer_count(framework: ZtFrameworkCode, answers: Iterable[Any]) -> int:
    """How many stored answers sit on a code the catalog does not have."""
    valid = all_codes(framework)
    return sum(1 for a in answers if a.capability_code not in valid and has_recorded_answer(a))


def retired_sentence(framework: ZtFrameworkCode, count: int) -> str | None:
    """The approved disclosure, or None when there is nothing to disclose."""
    if count <= 0:
        return None
    source = _SOURCE[framework]
    if count == 1:
        return (
            f"1 recorded answer belongs to a row that {source} does not have, so it is not scored."
        )
    return (
        f"{count} recorded answers belong to rows that {source} does not have, "
        "so they are not scored."
    )
