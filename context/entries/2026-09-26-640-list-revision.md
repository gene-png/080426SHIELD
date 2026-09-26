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
- The progress bar is a twin left alone, with a note at the site.

Tests: `test_capability_list_revision.py` drives the routes. Its set of edit
routes is derived from the router. Each guard was reverted on its own,
and each turned a named test red. The backfill test rewinds 0056 over lists
the API built. The web tests cover the stale, current and released states. No
existing test was edited.
