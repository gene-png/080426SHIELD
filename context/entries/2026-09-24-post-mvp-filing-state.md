# 2026-09-24: `post-mvp` is the filing rule's third state

Branch `feat/post-mvp-label-state`, base `0a831a7`.

## What changed

- **CLAUDE.md's filing rule** names `post-mvp` as a third legitimate state,
  beside `mvp-blocking` + a tier and `unowned-with-reason`. It is a decision,
  not a backlog, and not a trigger: one that must come back carries
  `Trigger-date:`.
- **`check_issue_labels.py`** accepts `post-mvp` off the board, with or
  without a tier. With `mvp-blocking`, the tier check still applies. The
  off-board message names all three states. The special-case suffix that
  called `post-mvp` "a state the rule does not name" is gone.
- **The filing rule's incident paragraph** (#184/#286) moved to D-086, to pay
  for the new clause under the size gate.

## Proof

- The tests were written first and went red: four failures, all on the new
  rows and messages.
- Red-on-revert: reverting only the predicate turned the two `post-mvp` rows
  and the message test red.
- On the live board, the gate reads 148 faults before this change and 115
  after. The 33 cleared are the `post-mvp` issues.

## Residual

Nothing puts deferred issues in front of anyone. `label:post-mvp` finds them,
and only a `Trigger-date:` brings one back.
