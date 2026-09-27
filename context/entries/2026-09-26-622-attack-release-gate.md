# 2026-09-26: an ATT&CK assessment with a Not verified row, or a Partial with no reason, is not approved or released (#622)

Branch `track2/attack-release-gate`, from `main` at `279d36f`.

This is D-092's release blocker, at the scope recorded on #622 on 2026-09-26.
#557's gap dispositions stay post-MVP and join the gate when #557 is built.
`coverage.WRITABLE` is unwidened.

## What changed

- **`attack/release_readiness.py`** holds the one predicate, in two forms: SQL
  for the release flip and Python for approve and for naming codes.
  - **Not verified** (`unable_to_determine`) blocks every assessment. The
    threshold is zero.
  - **A Partial with no `reason_code`** blocks under #620's rules only (option
    (b), the coordinator's call). A computed parent is exempt and is judged
    through its children (D-094). An assessment approved before #620 predates
    reason codes and is locked, so the clause could never be cleared there.
- **Approve** applies the predicate after recomputing parents, while the draft
  can still be fixed. The refusal names the technique panel's Reason select.
- **Release** passes the predicate as a `ParentGuard`, so the check and the
  RELEASED write are one statement. It is the backstop for an approved row that
  reaches this state by any path. An approved assessment is locked, so the
  refusal names what blocks it and gives no fix-it step.
- Both refusals are a typed 409, `attack_not_release_ready`. They carry the
  codes, a count, and the first ten codes in the message. The web shows the
  API's sentence, and a test pins that it reaches the release card.

## Blast radius, measured before choosing

On the dev database (read-only), 2 ATT&CK assessments are APPROVED or
RELEASED. Both are RELEASED under rule 1, and they have 0 Not verified rows and
532 Partial rows with no reason. Under option (b), neither is affected. No
rule-2 assessment is approved or released there. CI and prod are unknown.
