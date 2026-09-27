# 2026-09-26: Tech Debt step 2 classifies many rows at once (#641)

Branch `track1/bulk-classification`, from `main` at `e851e59`, with #685's
branch merged in (it reshapes the same table). "Classify" is read as the
keep / consolidate / cut disposition, the decision #639's approval gate
counts, not the security classification.

- API: `POST /tech-debt/capability-lists/{id}/items/disposition` with
  `{item_ids, disposition}`. All or nothing: a row outside the list is a typed
  422 `capability_items_not_in_list` and nothing is written; an empty
  selection is a typed 422 `no_items_selected`. `disposition` has no default,
  so omitting it is a 422, never "set to undecided". Same per-row effect as
  the single-row PATCH (the value, and `confidence_pct` cleared). One audit
  row, `capability_items.disposition_set`, names every item.
- Web: the step-2 table gets row checkboxes, a select-every-row box and a bulk
  bar, only when the workspace passes a bulk handler and the list is
  editable. Without the handler the table renders exactly as before, so the
  #643 layout tests are unchanged. `useRowSelection` is generic for ATT&CK
  gap triage (#557) to reuse.

Tests: 11 API tests through the endpoint, read back through the
consolidation plan; each guard (not-in-list, empty, confidence cleared,
tenant) was reverted on its own and turned a named test red. 9 table tests
and 3 workspace-wiring tests. No existing test was edited.

Admin screens only; the counts it changes are the consolidation plan's, the
same ones the single-row edit already changes.
