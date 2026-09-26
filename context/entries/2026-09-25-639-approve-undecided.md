# 2026-09-25: a capability list with undecided rows cannot be approved (#639)

Branch `track1/techdebt-approve-undecided`, cut from `origin/main`. Leaves #639
open for the owner to close after review.

## What was wrong

`POST /tech-debt/capability-lists/{id}/approve` approved a list whose step-2
review was unfinished. A row with `disposition` NULL (the model's own
"undecided", and the "Undecided…" option in the step-2 table) was frozen into
the approved membership while the consolidation plan's own summary still counted
it as undecided, so a deliverable could be finalized from a review nobody had
finished. Re-approving an already-approved list is refused the same way.

## What changed

- **`routes/tech_debt.py`.** Approval refuses with a typed 409,
  `capability_list_undecided_rows` (D-016), naming the count ("1 row is" / "N
  rows are") and pointing back to step 2 by its on-screen title. The refusal is
  enforced in the approve UPDATE's own WHERE (`NOT EXISTS` an undecided row),
  not only in the read before it, so a row set back to undecided between the
  check and the write is still refused. On a lost swap the route recounts and
  names whichever cause holds now. `undecided_row_count` is shared with
  `consolidation_plan_summary`, which used to count the same predicate in its own
loop, so the plan and the refusal cannot disagree.
- **No web change.** `proxyMessage` in `lib/tech_debt/client.ts` renders the
  typed `message` for any reason. e2e s29 and s38 already decide every row
  before approving; the demo seed writes the status directly.

## Tests

- The refusal, parametrised over one and two undecided rows. Both RED on the
  unfixed route.
- The race: a one-shot hook on `build_approved_membership`, which the route
  calls between its count and its UPDATE, sets a row back to undecided through a
  separate session. The test asserts the hook fired. It goes RED with the
  `no_undecided_rows` condition removed from the WHERE — see the PR body for the
  run.
- **Existing tests changed, and why.** Four tests approved a list whose rows
  were never decided, which is exactly the state #639 makes unapprovable. Their
  setup now decides the rows; no assertion was loosened. `_approve_list`
  ignored the approve response, so a refused approval would have left the
  following tests running on a draft list they believed approved. It now
  asserts 200.
