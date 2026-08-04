---
description: Cron-driven orchestrator for the autonomous sprint loop. Fires every N minutes (default every 10). Each fire dispatches a fresh-context Agent (Opus 4.7) to run either one task iteration or a checkpoint (full test suite + security audit). Detects queue completion or halt and auto-shuts the cron via CronDelete. Logs every fire to .claude/scheduler-debug.log.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, Agent, CronCreate, CronDelete, CronList
model: opus
---

# Sprint Loop Orchestrator (cron-driven, Agent-dispatched)

You are the orchestrator. Cron invokes you every N minutes. You do NOT do iteration work yourself. Each fire dispatches a fresh-context Agent that does one iteration of work and returns a short summary. The Agent has zero context from prior iterations; that is the entire point of this architecture.

Keep user-facing text minimal: one line per fire is enough. Reserve longer output for completion, halt, or unexpected errors.

---

## 0. Read state

Read `.claude/sprint-queue.json`. If missing, append a log line `stage=queue-missing` and tell the user the queue is gone. Do not CronCreate. End turn.

---

## 1. Bootstrap cron on first fire

If `queue.cron_job_id` is null or unset, this is the user's initial invocation rather than a cron fire.

- Call `CronCreate(cron: queue.cron_schedule || "*/10 * * * *", prompt: "/loop-sprint-cron", recurring: true)`.
- Store the returned id in `queue.cron_job_id` and save the queue.
- Tell the user the cron is now scheduled and continue with this fire as the first iteration (so the user does not wait 10 minutes for the first task).

---

## 2. Log the fire

Determine session identity:
- `pid = $$` (the orchestrator's process id; use `echo $$` via Bash).
- `cwd = $(pwd)`.
- `lock_holder` = contents of `.claude/sprint-queue.lock` if present, else `"free"`.

Append one line to `.claude/scheduler-debug.log`:

```
[<iso8601 UTC>] cwd=<cwd> orchestrator_pid=<pid> lock=<lock_holder | "free"> stage=enter
```

Each subsequent step that decides to skip, halt, complete, or dispatch should append its own line with `stage=<decision>`. This log is how you verify per-repo isolation when running two loops in parallel: the cwd field and the lock holder values should never collide between two loops in different repos.

---

## 3. Completion check

If every task in `queue.tasks` has `status=="done"`:

- Append log `stage=complete done=<n>/<n>`.
- Call `CronDelete(queue.cron_job_id)` and set `queue.cron_job_id=null`.
- Dispatch one final shutdown Agent (see §7) with the shutdown prompt.
- Save queue. Tell user the loop completed; report final commit sha.
- End turn.

---

## 4. Halt check

If `queue.halt.active == true`:

- Append log `stage=halted reason="<halt.reason>"`.
- Call `CronDelete(queue.cron_job_id)` and set `queue.cron_job_id=null`.
- Save queue. Tell user the halt reason in one sentence.
- End turn. (Cron is now off. To resume, the user clears the halt and re-invokes `/loop-sprint-cron`.)

---

## 5. Lock check

If `.claude/sprint-queue.lock` exists and the file's mtime is less than 10 minutes ago:

- Append log `stage=lock-contention holder="<lock contents>"`.
- End turn. (Cron will fire again on its next tick; the previous agent will be done by then in nearly all cases.)

If the lock exists but is stale (mtime > 10 min): delete it (the previous agent died) and proceed.

---

## 6. Decide iteration type: task or checkpoint

Let `done_count = tasks.filter(t => t.status=="done").length`.

If `(done_count - (queue.last_checkpoint_at || 0)) >= (queue.checkpoint_cadence || 4)`:

- This is a checkpoint fire.
- Increment `queue.checkpoint_count` (default 0).
- Update `queue.last_checkpoint_at = done_count`.

Else: this is a task fire.

Save the queue.

---

## 7. Dispatch the Agent (fresh context, Opus 4.7)

**Task fire:**

```
Agent({
  subagent_type: "general-purpose",
  model: "opus",
  description: "Sprint loop one iteration",
  prompt: TASK_AGENT_PROMPT
})
```

`TASK_AGENT_PROMPT`:

> You are executing one iteration of an autonomous sprint loop, in a fresh context. Read `.claude/commands/loop-sprint.md` and follow its instructions from §0 through §7 EXACTLY. Do NOT call ScheduleWakeup; the orchestrator handles scheduling. When the iteration is complete (committed, or halted), append one line to `.claude/scheduler-debug.log` of the form `[<iso>] agent_stage=done task=<id> commit=<sha or "halt"> outcome=<short>` and return a one-line summary to the orchestrator.

**Checkpoint fire:**

```
Agent({
  subagent_type: "general-purpose",
  model: "opus",
  description: "Sprint loop checkpoint",
  prompt: CHECKPOINT_AGENT_PROMPT
})
```

`CHECKPOINT_AGENT_PROMPT`:

> You are running a sprint loop checkpoint, in a fresh context. Read `CONTEXT.md` and `.claude/sprint-queue.json` to understand current state. Run the project's Playwright end-to-end suite (`npx playwright test --reporter=line`) and a security audit (`npm audit`, plus scan staged code for hardcoded credentials and OWASP-top-10 issues). If either finds something fixable in one pass, fix it test-first, commit on the current branch with a `chore(<queue.sprint>): checkpoint` style message, and append `agent_stage=checkpoint task=checkpoint result=fixed commit=<sha>` to `.claude/scheduler-debug.log`. If clean, append `result=pass`. If something is broken in a way you cannot fix in one pass without violating TDD, flip `queue.halt.active=true` with a clear `halt.reason` describing the issue and return. Do NOT bypass tests; do NOT use `--no-verify`.

**Shutdown fire (queue empty):**

`SHUTDOWN_AGENT_PROMPT`:

> The sprint loop has reached queue completion in a fresh context. Read `.claude/sprint-queue.json` to confirm all tasks `status=="done"`. Execute the following sequence:
>
> 1. **Deep audit.** Run `/debugloop` semantics: spawn parallel sub-audits for type errors, logic and runtime issues, spec compliance against the sprint doc named in `queue.sprint_doc` and `docs/architecture.md`, and test coverage gaps. Fix everything found, on the current branch, in commit-able chunks. If anything is broken in a way you cannot fix in one pass without violating TDD, flip `queue.halt.active=true` with a clear reason and stop here.
> 2. **Security audit.** Run `npm audit` to capture any new vulnerabilities introduced by the sprint's dependency additions. Scan staged and recently-committed code for hardcoded credentials and OWASP-top-10 issues. Fix or document. Note deferred items in the final PR description.
> 3. **Refresh CONTEXT.md.** Overwrite with a complete end-of-sprint snapshot: what shipped (each task with its commit sha), what got deferred (any T7/T8 halts the user has not applied), known issues, lessons learned. Format follows the existing CONTEXT.md style.
> 4. **Commit cleanups.** If steps 1-3 produced any changes, commit them on the current branch as `chore(<queue.sprint>): final audit and CONTEXT refresh`.
> 5. **Push the branch.** Run `gh auth status` first to confirm `queue.expected_gh_user` is the active account (`gh auth switch --user <queue.expected_gh_user>` if not). Then `git push origin <branch>`. The push triggers the pre-commit hook on staged files but git push does not run it again, so this is safe.
> 6. **Update the pull request.** If `queue.scratch` references a PR for this sprint, read the full commit log on this branch (`git log <branch> ^main --oneline`), then run `gh pr edit <pr-number> --body "$(...)"` with a refreshed body that includes: a new Summary section reflecting ALL commits on the branch (not just the original partial scope), the full task table from the queue (id, title, commit, status), a Test plan section covering the six gates + Playwright e2e + audit posture, an Out-of-scope section listing any halts still pending user apply. Preserve the existing PR title. If no PR exists yet, skip this step — the dev opens the sprint PR themselves.
> 7. **Append log.** Write `agent_stage=shutdown result=<pass|fixed|failed> pushed=<true|false> pr_updated=<true|false>` to `.claude/scheduler-debug.log`.
> 8. **Return one line summary** to the orchestrator with the final commit sha, push outcome, and PR url.

---

## 8. Record and exit

After Agent returns:

- Append log `stage=dispatched type=<task|checkpoint|shutdown> result="<agent's one-line summary>"`.
- Update `queue.scratch` with the same summary (truncate to 2KB).
- Save queue.
- End turn.

Cron will fire again in N minutes. If the queue is now done or halted, the next fire will hit §3 or §4 and tear down the cron automatically.
