"""#1120 (Option A, ruling item 1): the ratchet on writes to an APPROVED record.

Every route handler that can write a record table or one of its children is
DERIVED (`tests/_writer_scan.py`: the FK closure of the four record tables over
`Base.metadata`, plus `evidence_links`; then every `@router.*` handler, GET
included, followed through its calls). The derived set must equal the keys of
`WRITER_VERDICTS`, so a new writer without a verdict is red, and so is a verdict
whose handler no longer writes. Each verdict is one of:

* REFUSED: the handler answers 409 for an APPROVED record, pinned by the named
  test, which must exist;
* NEW RECORD: it writes a new record, never into an existing one;
* EXCLUDED: a named, reasoned exclusion (A1, A3 accepted and T, D, S confirmed
  by the advisor, #736 6136101129);
* NOT A WRITE: a scan over-match, read and ruled out.

Where a writer can still hide from the scan: raw SQL text; an attribute write in
a helper that names neither the model nor its status enum; a relationship
cascade; a writer that is not a route handler. A floor, not a census.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests._writer_scan import writers

pytestmark = pytest.mark.unit

API_ROOT = Path(__file__).resolve().parents[2]

#: handler -> (verdict, the REFUSED test node id, or the reason)
WRITER_VERDICTS: dict[str, tuple[str, str]] = {
    "app/routes/attack.py::approve_assessment": (
        "EXCLUDED",
        "T: a status transition into APPROVED (idempotent on APPROVED) or the release flip APPROVED -> RELEASED, with its ParentGuard (A4, #736 6136101129)",
    ),
    "app/routes/attack.py::confirm_coverage_citations": (
        "REFUSED",
        "tests/unit/test_approved_writes_refused.py::test_attack_confirm_coverage_citations_refuses_approved",
    ),
    "app/routes/attack.py::create_assessment": (
        "NEW RECORD",
        "NEW RECORD: writes a new record (reuses an open DRAFT or inserts the next version), never into an existing one",
    ),
    "app/routes/attack.py::discard_assessment": (
        "REFUSED",
        "tests/unit/test_approved_writes_refused.py::test_attack_discard_assessment_refuses_approved",
    ),
    "app/routes/attack.py::draft_dashboard": (
        "NOT A WRITE",
        "NOT A WRITE: an over-match; _row_as_the_run_left_it builds AttackCoverage rows in memory from a stored run result and never adds them to a session (#1178, pinned by test_attack_draft_dashboard.py::test_reading_the_draft_writes_nothing)",
    ),
    "app/routes/attack.py::finalize_attack_deliverable": (
        "EXCLUDED",
        "D: clears documents_stale only, a staleness flag, not content (A4)",
    ),
    "app/routes/attack.py::latest_assessment": (
        "NOT A WRITE",
        "NOT A WRITE: an over-match; _serialize_coverage assigns only to response-schema objects (r.pending_review = ...)",
    ),
    "app/routes/attack.py::patch_coverage": (
        "REFUSED",
        "tests/unit/test_approved_writes_refused.py::test_attack_patch_coverage_refuses_approved",
    ),
    "app/routes/attack.py::release_attack_deliverable": (
        "EXCLUDED",
        "T: a status transition into APPROVED (idempotent on APPROVED) or the release flip APPROVED -> RELEASED, with its ParentGuard (A4, #736 6136101129)",
    ),
    "app/routes/attack.py::review_computed_statuses": (
        "EXCLUDED",
        "A3: writes reviewed_* only, which no exporter reads; a review can only shrink the queue the release flip re-reads (ruled #736 6136101129)",
    ),
    "app/routes/attack.py::run_ai": (
        "REFUSED",
        "tests/unit/test_approved_writes_refused.py::test_attack_run_ai_refuses_approved",
    ),
    "app/routes/attack.py::start_assessment_revision": (
        "NEW RECORD",
        "NEW RECORD: inserts the next version as a new DRAFT copied from an APPROVED or RELEASED record, never writing the source; refused while the service has a draft (V6, the one-draft index) and while a run is in progress (refuse_while_running)",
    ),
    "app/routes/attack_scenarios.py::create_scenario": (
        "EXCLUDED",
        "S: writes what-if scenario rows pinned to the approved base, never the base's rows; no deliverable, dashboard or Risk path reads them (A4)",
    ),
    "app/routes/attack_scenarios.py::discard_scenario": (
        "EXCLUDED",
        "S: writes what-if scenario rows pinned to the approved base, never the base's rows; no deliverable, dashboard or Risk path reads them (A4)",
    ),
    "app/routes/attack_scenarios.py::run_scenario": (
        "EXCLUDED",
        "S: writes what-if scenario rows pinned to the approved base, never the base's rows; no deliverable, dashboard or Risk path reads them (A4)",
    ),
    "app/routes/csf.py::approve_assessment": (
        "EXCLUDED",
        "T: a status transition into APPROVED (idempotent on APPROVED) or the release flip APPROVED -> RELEASED, with its ParentGuard (A4, #736 6136101129)",
    ),
    "app/routes/csf.py::create_assessment": (
        "NEW RECORD",
        "NEW RECORD: writes a new record (reuses an open DRAFT or inserts the next version), never into an existing one",
    ),
    "app/routes/csf.py::discard_assessment": (
        "REFUSED",
        "tests/unit/test_approved_writes_refused.py::test_discard_assessment_refuses_approved",
    ),
    "app/routes/csf.py::export_playbook": (
        "EXCLUDED",
        "D: clears documents_stale only, a staleness flag, not content (A4)",
    ),
    "app/routes/csf.py::finalize_csf_deliverable": (
        "EXCLUDED",
        "D: clears documents_stale only, a staleness flag, not content (A4)",
    ),
    "app/routes/csf.py::get_self_assessment": (
        "NOT A WRITE",
        "NOT A WRITE: an over-match; _serialize_coverage assigns only to response-schema objects (r.pending_review = ...)",
    ),
    "app/routes/csf.py::latest_assessment": (
        "NOT A WRITE",
        "NOT A WRITE: an over-match; _serialize_coverage assigns only to response-schema objects (r.pending_review = ...)",
    ),
    "app/routes/csf.py::patch_answer": (
        "REFUSED",
        "tests/unit/test_approved_writes_refused.py::test_patch_answer_refuses_approved",
    ),
    "app/routes/csf.py::patch_dimension_score": (
        "REFUSED",
        "tests/unit/test_csf_working_profile_locked.py::test_a_dimension_score_patch_is_refused_once_approved",
    ),
    "app/routes/csf.py::patch_self_assessment_answer": (
        "REFUSED",
        "tests/unit/test_approved_writes_refused.py::test_patch_self_assessment_answer_refuses_approved",
    ),
    "app/routes/csf.py::release_csf_deliverable": (
        "EXCLUDED",
        "T: a status transition into APPROVED (idempotent on APPROVED) or the release flip APPROVED -> RELEASED, with its ParentGuard (A4, #736 6136101129)",
    ),
    "app/routes/csf.py::run_ai": (
        "REFUSED",
        "tests/unit/test_approved_writes_refused.py::test_run_ai_refuses_approved",
    ),
    "app/routes/csf.py::seed_profiles": (
        "REFUSED",
        "tests/unit/test_csf_working_profile_locked.py::test_seed_creates_the_missing_rows_on_an_approved_record_then_refuses",
    ),
    "app/routes/csf.py::start_assessment_revision": (
        "NEW RECORD",
        "NEW RECORD: inserts the next version as a new DRAFT copied from an APPROVED or RELEASED record, never writing the source; refused while the service has a draft (V6, the one-draft index) and while a run is in progress (refuse_while_running)",
    ),
    "app/routes/csf.py::submit_self_assessment": (
        "REFUSED",
        "tests/unit/test_approved_writes_refused.py::test_submit_self_assessment_refuses_approved",
    ),
    "app/routes/csf.py::upsert_gap_action": (
        "REFUSED",
        "tests/unit/test_csf_working_profile_locked.py::test_a_gap_action_upsert_is_refused_once_approved",
    ),
    "app/routes/intake.py::create_engagement": (
        "NEW RECORD",
        "NEW RECORD: writes a new record (reuses an open DRAFT or inserts the next version), never into an existing one: provisions a new Service with a v1 DRAFT",
    ),
    "app/routes/intake.py::submit_intake": (
        "NEW RECORD",
        "NEW RECORD: writes a new record (reuses an open DRAFT or inserts the next version), never into an existing one: provisions a new Service with a v1 DRAFT",
    ),
    "app/routes/tech_debt.py::add_capability_components": (
        "EXCLUDED",
        "A1: a Tech Debt APPROVED list stays editable; an edit makes the approval stale and release refuses it in the flip (#640, #657; ruled #736 6136101129)",
    ),
    "app/routes/tech_debt.py::approve_capability_list": (
        "EXCLUDED",
        "T: a status transition into APPROVED (idempotent on APPROVED) or the release flip APPROVED -> RELEASED, with its ParentGuard (A4, #736 6136101129); and A1: re-approving overwrites approved_membership, approved_at, approved_by and approved_revision",
    ),
    "app/routes/tech_debt.py::bulk_set_disposition": (
        "EXCLUDED",
        "A1: a Tech Debt APPROVED list stays editable; an edit makes the approval stale and release refuses it in the flip (#640, #657; ruled #736 6136101129)",
    ),
    "app/routes/tech_debt.py::confirm_excluded_row": (
        "EXCLUDED",
        "A1: a Tech Debt APPROVED list stays editable; an edit makes the approval stale and release refuses it in the flip (#640, #657; ruled #736 6136101129)",
    ),
    "app/routes/tech_debt.py::confirm_security_classification": (
        "EXCLUDED",
        "A1: a Tech Debt APPROVED list stays editable; an edit makes the approval stale and release refuses it in the flip (#640, #657; ruled #736 6136101129)",
    ),
    "app/routes/tech_debt.py::discard_capability_list": (
        "REFUSED",
        "tests/unit/test_approved_writes_refused.py::test_tech_debt_discard_capability_list_refuses_approved",
    ),
    "app/routes/tech_debt.py::extract_capability_list": (
        "NEW RECORD",
        "NEW RECORD: writes a new record (reuses an open DRAFT or inserts the next version), never into an existing one: the job inserts the next list version",
    ),
    "app/routes/tech_debt.py::include_excluded_row": (
        "EXCLUDED",
        "A1: a Tech Debt APPROVED list stays editable; an edit makes the approval stale and release refuses it in the flip (#640, #657; ruled #736 6136101129)",
    ),
    "app/routes/tech_debt.py::override_security_classification": (
        "EXCLUDED",
        "A1: a Tech Debt APPROVED list stays editable; an edit makes the approval stale and release refuses it in the flip (#640, #657; ruled #736 6136101129)",
    ),
    "app/routes/tech_debt.py::patch_capability_item": (
        "EXCLUDED",
        "A1: a Tech Debt APPROVED list stays editable; an edit makes the approval stale and release refuses it in the flip (#640, #657; ruled #736 6136101129)",
    ),
    "app/routes/tech_debt.py::release_tech_debt_deliverable": (
        "EXCLUDED",
        "T: a status transition into APPROVED (idempotent on APPROVED) or the release flip APPROVED -> RELEASED, with its ParentGuard (A4, #736 6136101129)",
    ),
    "app/routes/zt.py::approve_assessment": (
        "EXCLUDED",
        "T: a status transition into APPROVED (idempotent on APPROVED) or the release flip APPROVED -> RELEASED, with its ParentGuard (A4, #736 6136101129)",
    ),
    "app/routes/zt.py::create_assessment": (
        "NEW RECORD",
        "NEW RECORD: writes a new record (reuses an open DRAFT or inserts the next version), never into an existing one",
    ),
    "app/routes/zt.py::discard_assessment": (
        "REFUSED",
        "tests/unit/test_approved_writes_refused.py::test_discard_assessment_refuses_approved",
    ),
    "app/routes/zt.py::finalize_zt_deliverable": (
        "EXCLUDED",
        "D: clears documents_stale only, a staleness flag, not content (A4)",
    ),
    "app/routes/zt.py::get_self_assessment": (
        "NOT A WRITE",
        "NOT A WRITE: an over-match; _serialize_coverage assigns only to response-schema objects (r.pending_review = ...)",
    ),
    "app/routes/zt.py::latest_assessment": (
        "NOT A WRITE",
        "NOT A WRITE: an over-match; _serialize_coverage assigns only to response-schema objects (r.pending_review = ...)",
    ),
    "app/routes/zt.py::patch_answer": (
        "REFUSED",
        "tests/unit/test_approved_writes_refused.py::test_patch_answer_refuses_approved",
    ),
    "app/routes/zt.py::patch_self_assessment_answer": (
        "REFUSED",
        "tests/unit/test_approved_writes_refused.py::test_patch_self_assessment_answer_refuses_approved",
    ),
    "app/routes/zt.py::release_zt_deliverable": (
        "EXCLUDED",
        "T: a status transition into APPROVED (idempotent on APPROVED) or the release flip APPROVED -> RELEASED, with its ParentGuard (A4, #736 6136101129)",
    ),
    "app/routes/zt.py::run_ai": (
        "REFUSED",
        "tests/unit/test_approved_writes_refused.py::test_run_ai_refuses_approved",
    ),
    "app/routes/zt.py::start_assessment_revision": (
        "NEW RECORD",
        "NEW RECORD: inserts the next version as a new DRAFT copied from an APPROVED or RELEASED record, never writing the source; refused while the service has a draft (V6, the one-draft index) and while a run is in progress (refuse_while_running)",
    ),
    "app/routes/zt.py::submit_self_assessment": (
        "REFUSED",
        "tests/unit/test_approved_writes_refused.py::test_submit_self_assessment_refuses_approved",
    ),
}


def test_every_derived_writer_has_a_verdict_and_every_verdict_a_writer() -> None:
    derived = set(writers(API_ROOT))
    assert derived - set(WRITER_VERDICTS) == set(), "writers with no verdict"
    assert set(WRITER_VERDICTS) - derived == set(), "verdicts for handlers that no longer write"


@pytest.mark.parametrize("handler", sorted(WRITER_VERDICTS))
def test_each_verdict_is_well_formed(handler: str) -> None:
    verdict, detail = WRITER_VERDICTS[handler]
    assert verdict in ("REFUSED", "NEW RECORD", "EXCLUDED", "NOT A WRITE"), handler
    assert detail.strip(), handler
    if verdict != "REFUSED":
        return
    path, _, test = detail.partition("::")
    source = (API_ROOT / path).read_text()
    assert re.search(rf"^def {re.escape(test)}\(", source, re.M), (handler, detail, "no such test")
