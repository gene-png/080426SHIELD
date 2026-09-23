# 2026-09-23 — Batched AI calls keep the request's correlation id

Branch `fix/batched-ai-calls-keep-correlation-id`, base `df7d5b7`. This is the
work that came out of "item 3" (two audit-spine defects). **Both of its premises
were measured before anything was built, and neither held as written.**

## What item 3 said, and what the dev stack showed (2026-09-23)

| claim | measured |
| --- | --- |
| `audit()` takes no `correlation_id`, so audit rows cannot be joined to LLM calls | `audit()` stamps `correlation_id_var.get()` itself. **834 of 850** audit rows carry one; all 16 without one are seed-script actions with no request behind them. |
| the join is impossible | The broken side is **`llm_calls`**: 5 of 57 rows carry one, and **0 of 52** `mitre_map` rows. |
| disabling a user erases attribution (`ondelete="SET NULL"`) | Deactivation sets `is_active` and keeps the row. A delete is **refused**: the cascade is an UPDATE on `audit_entries`, and the append-only trigger rejects it. Filed as #486. |

## What was wrong

`_run_mitre_map_batched` (`routes/attack.py`) and `_run_risk_synthesize_batched`
(`routes/risk.py`) hand each batch to a `ThreadPoolExecutor`. A pool thread
starts with an empty context, so `correlation_id_var` read `None` there, and every
`llm_calls` row a batch wrote lost the request's id. The unbatched jobs
(`extract.capabilities`, `zt_score`) carried theirs, which is why the loss sat in
exactly one purpose on the dev stack.

## What changed

Each batch runs in `contextvars.copy_context().run`, with a fresh copy per submit,
because one `Context` cannot be entered by two threads at once. Nothing under
`app/models/**` changed, and there is no migration.

## Proof

One test per runner, each through the real endpoint with an `X-Request-ID`,
reading `llm_calls.correlation_id` back and requiring more than one batch. Each
went red on its own revert, with the rows reading exactly `[None, None, …]`.
The attack/risk test files: 95 passed.
