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

## 2026-10-15: the owner's spec (#736, item C)

- **The body checks confirm the queued head is the one being merged.** Both
  resolver steps pass the event's `merge_group.base_sha` and `head_sha`;
  `merge_group_pr.py` then requires the group head's tree to equal
  `git merge-tree --write-tree <base_sha> <PR head.sha>`, fetching the PR head
  by sha when the clone lacks it. A PR pushed after it was queued, a group
  holding a second PR, or a head that conflicts with the base is exit 2 with
  no output written. Method-agnostic: squash and merge-commit groups both pass
  (`tests/gates/merge_group_head.sh`, real git).
- **The audit must name that head.** On merge_group only, `check_audit_evidence
  --head-sha` requires the `## Adversarial audit` section to contain a 7-to-40
  hex prefix of the PR's current head (exit 1 if not, 2 if the head file is
  unreadable). All 20 of the latest merged PRs (1039 to 1162) already did.
- **Recorded payloads.** `tests/unit/test_merge_group_payloads.py` replays
  octokit's recorded `checks_requested` payload, and two copies differing only
  in `head_ref` (unparseable; a PR that does not exist), through both
  workflows' resolver steps as written.
- **What every required check reads** is pinned by
  `tests/unit/test_merge_group_event_reads.py`: no checkout overrides `ref:`,
  no step reads pull_request-only context unless it is pull_request-only, and
  no job a required check `needs` has a condition other than `always()`.
