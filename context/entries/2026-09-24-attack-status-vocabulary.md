# 2026-09-24: the ATT&CK status vocabulary, slice 1 (#554, D-092)

Branch `track2/attack-status-vocabulary`, base `20f747f`.

## Why

405 of 633 techniques were Partial in a released assessment, with no reason
and no action. The owner decided a vocabulary on #554 that separates three
unlike claims the single Partial status carried: partly defended, not
verified, and out of the client's reach.

## What this slice does

- **Six statuses.** The new ones are `outside_control_surface` and
  `unable_to_determine`, both outside the assessed denominator.
- **A reason code per status**, valid only for that status:
  - seven for Partial;
  - `platform_absent` for N/A;
  - three sub-cases for outside the control surface;
  - `unable_to_determine` carries a narrative instead.
- **Migration 0053** adds `attack_coverage.reason_code` and
  `attack_coverage.narrative`, both nullable.
- **`coverage_pct` is over assessed rows only.** The two new counts ride on the
  heatmap, overall and per tactic.
- **PATCH refuses an impossible pairing** with a typed 422 and drops a reason
  that no longer fits a changed status.

## Not in this slice

- **The prompt and parser (c2):** until then the AI produces no reason codes.
- **The release gate and the data-quality exception (c3).** The gate must be
  built new, because nothing gates release on `unconfirmed_citations` today.
  The exception ships only with its disclosure. c3 also covers the reporting
  surfaces and the test that no surface drops the not-verified count.
- **The workspace UI (c4).**

## Merge order

Migration 0053 chains from 0051 because #562's 0052 is not on main. Whichever
of the two merges second re-points its `down_revision`.
