"""DoD capabilities whose levels cannot reach a target are capped or disclosed (#839).

Under the approved prompt's rule C4, a DoD capability with no Advanced activity
can never score 3, and one with no Target activity can never score 2. Gene's
decision and the advisor's ruling 15 (#736 comment 5986057990, read (a) on
#838 comment 6023694715):

* no Advanced activity: the EFFECTIVE target is capped at 2, the highest level
  the capability defines, and each capped capability is disclosed (copy C1);
* no Target activity: the target is NOT changed; when it is 2, each such
  capability is disclosed as going from Below Target straight to Advanced
  (copy C2).

Which capabilities have which levels is read from the committed extraction,
never from the catalog, and the sentences are the approved copy, verbatim.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pytest

from app.zt.catalog import capabilities
from app.zt.maturity import ZtFrameworkCode
from app.zt.scoring import analyze_gaps, effective_target_stages
from app.zt.target_caps import target_cap_sentences
from tests._paths import find_zt_source

pytestmark = pytest.mark.unit

_FW = ZtFrameworkCode.DOD_ZTRA
_DOD = find_zt_source(Path(__file__).resolve(), "dod") or Path("/nonexistent/reference-docs/dod")


def _levels() -> dict[str, set[str]]:
    path = _DOD / "dod_zt_2025_rows.json"
    if not path.is_file():
        pytest.fail(f"{path} is not readable: the DoD extraction is the spec (#839).")
    src = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, set[str]] = defaultdict(set)
    for a in src["activities"]:
        out[a["id"].rsplit(".", 1)[0]].add(a["level"])
    return out


def _code(dod_number: str) -> str:
    return next(c.code for c in capabilities(_FW) if c.dod_number == dod_number)


def test_no_advanced_capabilities_are_capped_at_target_and_only_they() -> None:
    levels = _levels()
    no_advanced = {_code(n) for n, lv in levels.items() if "advanced" not in lv}
    assert len(no_advanced) == 15  # the extraction's own count, settled per cell
    applied = effective_target_stages(_FW, {}, 3)
    assert {code for code, t in applied.items() if t == 2} == no_advanced
    assert {code for code, t in applied.items() if t == 3} == set(applied) - no_advanced


def test_a_capped_capability_at_stage_two_is_no_gap_and_is_disclosed() -> None:
    capped = _code("1.1")  # User Inventory: Target activities only
    other = _code("1.2")  # Conditional User Access: Target and Advanced
    answers = {c.code: None for c in capabilities(_FW)} | {capped: 2, other: 2}
    gap = analyze_gaps(_FW, answers, target_stage=3)
    assert other in {g.code for g in gap.gaps}  # what must appear, first
    assert capped not in {g.code for g in gap.gaps}
    assert capped in gap.capped_target_codes
    assert other not in gap.capped_target_codes
    assert (
        "1.1 User Inventory has no DoD Advanced activities, so its target is Target (2)."
        in target_cap_sentences(gap)
    )


def test_a_target_of_two_keeps_and_discloses_the_no_target_capabilities() -> None:
    levels = _levels()
    no_target = sorted(n for n, lv in levels.items() if "target" not in lv)
    assert no_target == ["3.5", "6.4", "7.6"]
    applied = effective_target_stages(_FW, {}, 2)
    # Reading (a): the client's target is not changed.
    assert {applied[_code(n)] for n in no_target} == {2}
    gap = analyze_gaps(_FW, {c.code: 1 for c in capabilities(_FW)}, target_stage=2)
    assert set(gap.no_target_level_codes) == {_code(n) for n in no_target}
    sentences = target_cap_sentences(gap)
    assert (
        "3.5 Continuous Monitoring and Ongoing Authorizations has no DoD Target "
        "activities, so it moves from Below Target straight to Advanced."
    ) in sentences
    # A target of 2 caps nothing: 2 is every capability's reachable ceiling or below.
    assert gap.capped_target_codes == ()


def test_a_target_of_three_mentions_no_missing_target_level() -> None:
    gap = analyze_gaps(_FW, {c.code: 1 for c in capabilities(_FW)}, target_stage=3)
    assert gap.capped_target_codes  # the caps apply: what must appear, first
    assert gap.no_target_level_codes == ()


def test_cisa_is_never_capped() -> None:
    fw = ZtFrameworkCode.CISA_ZTMM_2_0
    gap = analyze_gaps(fw, {c.code: 1 for c in capabilities(fw)}, target_stage=4)
    assert gap.total_gap_count == len(capabilities(fw))
    assert gap.capped_target_codes == ()
    assert gap.no_target_level_codes == ()
    assert target_cap_sentences(gap) == []


# --- The levels that decide every cap, tied to the PDF (review round 2, F2) ---
#
# The tests above read the levels from the committed extraction, so a wrong
# level in the extraction would move the caps and keep every test green. These
# two lists were typed from the PDF read with a DIFFERENT engine:
# `pdftotext -raw ZT-CapabilitiesActivities.pdf` (poppler), not pdfplumber.
# For each activity, the level is the first "Target Level" / "Advanced Level"
# after its id line; three activities (4.7.5, 6.2.3, 6.6.3) mention the other
# level later in their prose, and each was read by eye: the level cell agrees
# with the first match. Read on 2026-10-08; 152 activities, 45 capabilities.

#: Capabilities with no Advanced activity: their maximum is Target (2).
_PDF_NO_ADVANCED = (
    "1.1",
    "1.7",
    "2.5",
    "2.6",
    "3.1",
    "3.3",
    "4.1",
    "4.2",
    "5.1",
    "5.3",
    "6.3",
    "6.6",
    "7.1",
    "7.3",
    "7.5",
)
#: Capabilities with no Target activity: disclosed only (reading (a)).
_PDF_NO_TARGET = ("3.5", "6.4", "7.6")


def test_the_served_maximum_of_every_capability_is_the_pdfs() -> None:
    from app.zt.target_caps import max_stage_for

    served = {c.dod_number: max_stage_for(_FW, c.code) for c in capabilities(_FW)}
    assert len(served) == 45  # every capability is read, first
    assert sorted(n for n, top in served.items() if top == 2) == sorted(_PDF_NO_ADVANCED)
    assert {n for n, top in served.items() if top == 3} == set(served) - set(_PDF_NO_ADVANCED)


def test_the_served_no_target_capabilities_are_the_pdfs() -> None:
    gap = analyze_gaps(_FW, {c.code: 1 for c in capabilities(_FW)}, target_stage=2)
    assert sorted(gap.no_target_level_codes) == sorted(_code(n) for n in _PDF_NO_TARGET)
