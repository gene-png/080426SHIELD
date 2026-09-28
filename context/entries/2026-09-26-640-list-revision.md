# 2026-09-26: an approved Tech Debt list edited afterwards must be approved again (#640, D-102)

Branch `track1/techdebt-edit-revision`, from `main` at `b5f5448`. Migration
0056 (`capability_lists.revision`, `approved_revision`), chaining from #658's
0055, per the owner's rule and the coordinator's design on #640. Stacked on
`track1/access-token-cutoff` (#670), which carries 0055.

- Every step-2 edit route increments `revision` (`_record_edit`). Approve's
  compare-and-swap records the revision it read, and refuses when an edit lands
  mid-approval.
- Finalize and release refuse a stale approval: typed 409
  `capability_list_edited_since_approval`, naming step 3.
- The list response carries `approval_current`. In the workspace, step 3
  shows "Approve again" and step 4 says why it is blocked. The classification
  queue is editable until release. Step 3's description no longer says
  approval "locks" the inventory, which was never true.
- A lock-only PATCH is not an edit.
- A deliverable records the list revision it was rendered from
  (`deliverables.capability_list_revision`, also in 0056). Release refuses one
  that does not match the list's `approved_revision`, including a NULL from
  before 0056: typed 409 `deliverable_predates_approval`, naming Re-finalize.
  For a NULL the message says nothing confirms the rows, not that the
  deliverable predates the approval.
- #709's bulk-disposition route calls `_record_edit` and has a driver.
- The progress bar is a twin left alone, with a note at the site.

Tests: `test_capability_list_revision.py` drives the routes. Its set of edit
routes is derived from the router. Each guard was reverted on its own,
and each turned a named test red. The backfill test rewinds 0056 over lists
the API built. The web tests cover the stale, current and released states.
One existing test was edited, on the coordinator's verdict (overturnable):
`test_migration_0051_backfill.py`'s `_freeze` selects the two columns it
reads rather than the whole `Deliverable`, which at revision 0051 has no
`capability_list_revision` column. Its assertions are unchanged.

Advisor review at `1d012e4` (2026-09-28) found two defects, fixed by the
advisor on this branch:

- F1: release of an older deliverable after a newer one had released the list,
  and of a deliverable with no `parent_version`, skipped the flip's guard. The
  release route now refuses both before releasing. Tests:
  `test_an_older_deliverable_is_refused_after_the_list_is_released`,
  `test_a_deliverable_with_no_parent_version_is_refused`; both go red with the
  route check removed.
- F2: an inline row edit left step 3 showing "Approved" until reload. The
  workspace re-reads the list after an edit to an approved list. The web test
  "an inline row edit on an approved list re-enables Approve again" goes red
  with the re-read removed.
