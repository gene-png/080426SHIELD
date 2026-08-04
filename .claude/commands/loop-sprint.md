---
description: One iteration of an autonomous sprint loop. Generic, not sprint-coupled. Reads .claude/sprint-queue.json for branch, project config, task list, and per-task instructions. Replace the queue file at the start of each sprint; the skill never changes.
argument-hint: (no arguments; reads state from .claude/sprint-queue.json)
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, ScheduleWakeup
model: opus
---

# Sprint Loop, One Iteration

Generic loop driver. One iteration of work. All sprint-specific state lives in `.claude/sprint-queue.json`. The skill itself never edits between sprints. Replace the queue at the start of each new sprint.

Be terse with user-facing text, the user is not watching every wake. Reserve text output for: which task you picked, what verified, what committed, and the halt-or-continue decision at the end.

Every step that says **HALT** means: set `halt.active=true` with a clear `halt.reason` in the queue, write a one-sentence summary to the user, and do **not** call `ScheduleWakeup`. The loop ends until the user clears the halt.

---

## 0. Preflight guards (HALT on violation)

1. Read `.claude/sprint-queue.json`. If missing, HALT with reason `queue-missing`.
2. If `halt.active==true`, do nothing and do not reschedule. Tell the user the existing halt reason.
3. CWD must equal the queue's `working_dir` field (a path string; compare case-insensitively on Windows). If not, HALT. (`working_dir` is machine-local — the launch checklist has each developer set it in their runtime copy of the queue.)
4. Check for `.claude/sprint-queue.lock`. If present and mtime is within the last 10 minutes, another iteration is running, HALT with `lock-contention`. Otherwise, claim the lock (write `<pid>\n<iso8601>` into the file).
5. Confirm `gh auth status` shows active user matching the queue's `expected_gh_user` field (also machine-local; if the active account differs but the expected account is logged in, run `gh auth switch --user <expected>` and re-check before halting). If not, HALT with `gh-account-mismatch` and tell the user the expected value.
6. ONLY IF the queue defines a non-null `expected_gcloud_config` field: confirm `gcloud config configurations list --filter=is_active=true --format="value(name)"` returns it; if not, HALT with `gcloud-config-mismatch`. (You may still proceed if the next task is `risk=low`, but for any `gcp-mutating` task this is a hard halt.) Projects with no GCP surface simply omit the field — skip this step entirely, do not halt on its absence.
7. Confirm git branch matches the queue's `branch` field. If on `main` and `started_at` is null, run `git checkout -b <branch>`. If on any other branch, HALT.

---

## 1. Orient

Read in order:
- `.claude/sprint-queue.json` (already read in §0)
- `CONTEXT.md` (skim)
- The queue's `sprint_doc` field if set (look up the section for the task you will pick by grepping the task id)
- `git status --short`
- `git log --oneline -5`

If `git status` shows uncommitted changes:
- If `current_task_id != null` and all dirty files are in that task's `expected_paths`, this is a resume, continue at **§5 Verify**.
- If `current_task_id != null` but dirty files are outside `expected_paths`, HALT with `dirty-tree-mismatch`.
- If `current_task_id == null` and tree is dirty at all, HALT with `unattributed-dirty-tree`.

---

## 2. Pick next task

Iterate tasks in array order. Pick the first task where:
- `status == "pending"`
- every id in `depends_on` has `status == "done"` in the queue

If no task qualifies:
- If every remaining task is `done`, write a final CONTEXT.md snapshot (overwrite, not append) summarizing what shipped this sprint, release the lock, and **do not call ScheduleWakeup**. The loop is complete. Tell the user.
- If remaining tasks are all `blocked-risk` or `needs_user`, HALT with `awaiting-user` and list which tasks need what action.

Set `current_task_id` to the picked task. If `started_at` is null, set it to now. Save the queue.

---

## 3. Branch

You should already be on the queue's `branch` from §0. Re-confirm. Do not switch branches mid-iteration.

---

## 4. Execute

**The task's `notes` field is the task-specific instruction set.** Read it carefully. The notes are the source of truth for what to write, what to verify, what to commit. The notes were authored when the queue was seeded; treat them as the playbook.

Also consult the queue's `sprint_doc` (e.g. `SPRINT_3.md`) if set, by grepping for the task id heading. The doc may have more narrative context than the queue notes.

Default execution shape (Test-Driven Development):
1. Write the failing test(s) first under `tests/unit/` or `tests/e2e/`. For non-code tasks (documentation, infrastructure as code), substitute a verification predicate from the task's `verify` array.
2. Confirm the test fails by running it once.
3. Implement the minimum to pass.
4. Re-run the test; it must now pass.

For tasks marked `risk=gcp-mutating`: write the change, run `terraform validate`, run `terraform plan -out=<task-id>.tfplan` with explicit `--account` and `--project` flags on every `gcloud` call. **Do not run `terraform apply`.** Commit the `.tf` change. Set `status=blocked-risk`, write the apply command into `scratch`, and HALT.

---

## 5. Verify

For every task, run the gates that apply:
- Every command in the queue's `gates` array must exit 0. These are the repo-wide
  gates (this project runs its test/typecheck gates inside Docker containers;
  the queue encodes the exact commands, including the required PATH export).
- Playwright specs relevant to the task (the task's `verify` array lists them).

Plus any verification predicates listed in the task's own `verify` array.

If any gate fails:
- Increment `attempts`.
- If `attempts < 2`: try a corrective fix and re-run gates.
- If `attempts >= 2`: set `status=needs_user`, write a concise diagnosis into `scratch`, HALT.

---

## 6. Commit

- Stage **only** the files in the task's `expected_paths` (use `git add <explicit-files>`, never `git add -A`).
- Never commit secrets, `.env`, or credentials; do not bypass repo pre-commit hooks with `--no-verify`.
- Write a conventional commit message: `<type>(<scope>): <subject>`. Types: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `ci`. Subject under 70 chars. Body explains the why in 1-2 sentences. End the body with the current model's co-author line, e.g. `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Capture the new commit SHA.

---

## 7. Record

Update the queue:
- Set the task's `status="done"` (or `blocked-risk` for tasks that produced a terraform plan and halted for apply).
- Write the commit SHA into the task's `commit` field.
- Set `current_task_id=null`.
- Update `scratch` with one line summarizing what landed.

Save the queue.

---

## 8. Release lock and return

- Delete `.claude/sprint-queue.lock`.
- Append one line to `.claude/scheduler-debug.log`: `[<iso>] agent_stage=done task=<id> commit=<sha or "halt"> outcome=<short>`.
- Return a one-line summary to the orchestrator: which task completed, the commit SHA, and what's next (or "halted: <reason>").
- Do NOT call ScheduleWakeup. The orchestrator at `.claude/commands/loop-sprint-cron.md` owns scheduling; this skill is now invoked as a fresh-context Agent per fire by that orchestrator. Self-scheduling would create duplicate fires.
