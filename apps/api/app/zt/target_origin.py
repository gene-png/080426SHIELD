"""#1343: which applied per-capability ZT targets have no recorded origin.

#982 (migration 0076) records who set a per-capability target
(`zt_answers.target_source`). A NULL origin means the target was stored before
0076, and some of those were set by earlier AI runs. The consultant's
questionnaire discloses it; the client outputs (deliverable, dashboard, risk
register) reuse the same approved sentence (#736 6225076633).

ONE predicate for the deliverable and the client ZT dashboard, so they
cannot disagree about which targets are unrecorded. A target is listed when
the gap engine APPLIES it (`capability_target_override`, the predicate
`effective_target_stages` uses); an unusable stored value falls back to the
engagement stage, so it is not. An applied override can still equal the
engagement stage, or meet it at a DoD capability's cap, and so change no
number; it is listed anyway, because the sentence is about who set the
target, which stays true.

The Risk Register applies a stored per-capability target RAW
(`routes/risk.py`), not through `capability_target_override`; the two agree
on every value the writers store today, and the register says how it uses
this predicate where it calls it.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from app.zt.catalog import capabilities
from app.zt.maturity import ZtFrameworkCode
from app.zt.scoring import capability_target_override

#: Approved verbatim at #736 comment 6220094031 item 5. The web bundle carries
#: the same sentence in `ZtQuestionnaire.tsx` (`TARGET_ORIGIN_NOT_RECORDED`).
TARGET_ORIGIN_NOT_RECORDED = (
    "Who set this target is not recorded. An earlier AI run may have set it."
)


class _TargetRow(Protocol):
    capability_code: str
    target_stage: object
    target_source: str | None


def unrecorded_target_codes(
    framework: ZtFrameworkCode, rows: Iterable[_TargetRow]
) -> tuple[str, ...]:
    """The codes, in catalog order, whose applied per-capability target has no
    recorded origin. A code not in `framework` is ignored."""
    by_code = {r.capability_code: r for r in rows}
    codes = []
    for cap in capabilities(framework):
        row = by_code.get(cap.code)
        if row is None or row.target_source is not None:
            continue
        if capability_target_override(framework, row.target_stage) is not None:
            codes.append(cap.code)
    return tuple(codes)
