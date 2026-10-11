# 2026-10-01: Run-AI runs in the background (#645, with #504 and #271; D-104)

Branch `track2/ai-runs-background`, PR #756. Migration 0057 (`ai_runs`, and
`llm_calls.ai_run_id`).

- A Run-AI POST answers 202 with a run. The refusals that need no AI stay
  synchronous, with the status and reason they always had. A background job
  does the work and finishes the run with a compare-and-swap on RUNNING, in
  the same transaction as the apply. A reaped run never applies late.
- `serves` is required. Offline acknowledged while the provider would go live
  is a typed 409 `ai_status_changed` (#504). One RUNNING run per service and
  purpose, by a partial unique index; a second POST joins in the same mode and
  on the same subject, or is refused.
- Every failure is a FAILED run with a typed reason. `charged_likely` is read
  from the run's own `llm_calls` rows, each of which now names its run, and
  carries the request's correlation id.
- Edit lock over router-derived route sets for ATT&CK, CSF and ZT; discard
  stays open. Tech Debt has no lock (an extraction writes only a new version).
  A row edited at or after the run's start is kept and counted.
- Reap on read: a RUNNING run from another boot, absent from this process's
  live set, or past its deadline plus a margin is ended when it is next read.
- The workspaces poll the run, say "could not check" rather than "failed",
  show the lock and its deadline, and read every disclosure from the last
  completed run, so a partial run is still visible after a reload (#271).

Order of landing: framework and ATT&CK, then Tech Debt extraction, CSF and ZT,
each in its own commit, then a merge of `main` for #550. Risk is not changed (set
aside by Gene, 2026-09-27).
