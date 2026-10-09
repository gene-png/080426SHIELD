# 2026-09-26: every required check runs on a merge-queue entry

Branch `track1/merge-group-body-checks`, cut from `origin/main` at `e9b1bdb`.
Owner-ordered: Gene's instruction was to add `merge_group` to the CI workflow
triggers; he enables the merge queue after this lands. Comes back to him under
merge-rule condition 5 (`.github/workflows/**`, `apps/api/scripts/**`,
`apps/api/tests/**`).

## What changed

- **Both workflows trigger on `merge_group`.** The seven required contexts come
  from `ci.yml` (Python, Web, Secret scan, E2E, Demo) and `audit-gate.yml` (the
  two body checks). A workflow without the trigger never reports on the queue's
  commit, and the queue waits forever.
- **No required job has a job-level `if:`.** A skipped required job reports
  success, so a condition excluding `merge_group` would be a silent green on the
  one event the queue decides on. `tests/unit/test_merge_group_triggers.py`
  pins the trigger and the absence of a condition for every required context.
  The contexts are a constant in that test, read from branch protection on
  2026-09-26; update it if branch protection changes.
- **The two body checks read the queued PR's CURRENT body.** On `merge_group`
  there is no `github.event.pull_request`. `apps/api/scripts/merge_group_pr.py`
  parses N from `gh-readonly-queue/main/pr-<N>-<sha>` and fetches PR N's title,
  body, author, files, commits, closing references and diff with the workflow
  token. An unparseable ref, a failed fetch, or GitHub answering with a
  different PR exits 2 and deletes every requested output, so no stale body is
  read. The earlier pull_request run is never trusted: the description can
  change after it.
- **The Dependabot exemption keys on a "Who opened the PR" step**, which reads
  the event's `pull_request.user.login` on pull_request and the fetched PR's
  `user.login` on merge_group, and exits 2 on an empty author. Keyed on the
  event alone, the author is empty on merge_group and a bot PR would face an
  audit gate its body can never satisfy.
- **Secret scan on merge_group runs the gitleaks CLI directly.**
  `gitleaks-action@v3` exits 1 for any event outside push, pull_request,
  workflow_dispatch and schedule. On merge_group only, `ci.yml` runs gitleaks
  8.24.3 (the action's default), checksum-verified before it executes, through
  `scripts/gitleaks-merge-group.sh`, which refuses a range with no non-merge
  commits (exit 2): a merge-shaped queue group would otherwise scan nothing and
  pass. Remove the step when the action supports the event.
- **Not on merge_group:** the three non-required `audit-gate.yml` jobs (merge
  rule text, migration declared, compose content) and the D-number step inside
  "No accidental issue closes". All ran on the PR head; the D-number step
  judges commit subjects, which cannot change without a push, and a push
  removes the PR from the queue.
- **`CLAUDE.md`**: the direct-push sentence said `audit-gate.yml` triggers on
  `pull_request` only. It now says the workflow never runs on a push, which is
  the property that sentence relies on.

## Existing tests changed, by the coordinator's verdict

Three in `test_audit_gate_dependabot_exemption.py` repinned by equality to the
author step; one in `test_compose_unchanged.py` now allows exactly one
job-level condition on the compose job. The PR body carries the verdicts.
