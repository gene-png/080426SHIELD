# 2026-09-23 — #479: every AI job's output budget is chosen, and a registry gate keeps it so

Branch `fix/ai-output-budget-per-purpose`, base `df7d5b7`. Refs #479, **which stays
open**: its acceptance asks for `csf_score` and `zt_score` to be sized against a
real assessment, and that needs a live, billable run nobody has authorised.

## What was wrong

`AIJob.call_purpose` is `purpose or name`, so the five effective purposes are
`extract.capabilities`, `csf_score`, `zt_score`, `mitre_map`, `risk_synthesize`.
`_MAX_OUTPUT_TOKENS_BY_PURPOSE` listed two. The other three took the shared 8192
because nobody chose otherwise.

Measured on the dev stack's `llm_calls` before changing anything: a live
`extract.capabilities` overran 8192 (`stop_reason=max_tokens`, 00:47 UTC), and
its retry finished at **8117 of 8192**. No live `csf_score` or `zt_score` has
ever run there.

## What changed

| purpose | Anthropic (streamed) | OpenAI / Gemini / Vertex (not streamed) | basis |
| --- | --- | --- | --- |
| `extract.capabilities` | 8192 → **64000** | 8192, unchanged | measured, above |
| `csf_score` | 8192 → **64000** | 8192, unchanged | **estimate**: 318 rows at 100–575 tokens each. 64000 fits only the low end, and batching per tier is the real fix |
| `zt_score` | 8192, now **chosen** | 8192, unchanged | 3 short fields per capability, so a larger budget buys nothing |
| `mitre_map`, `risk_synthesize` | unchanged | unchanged | |

**The non-streamed adapters are byte-for-byte unchanged from `main`, on purpose.**
A per-model ceiling list was tried first. Three review rounds each found a model
it missed (`gpt-4.1`, then `gpt-5-chat-latest`), and every miss was an HTTP 400 on
a configuration that worked at 8192. A list of provider limits cannot be
complete; "these adapters are unchanged" can be, and
`test_the_non_streamed_adapters_send_what_main_sent_for_every_purpose` pins it
for every registered purpose. Raising them is its own change, with #485.

`test_every_registered_job_has_a_chosen_output_budget` walks the registry through
the public `registered_jobs()` / `get_job()`. A grep for `purpose="..."` literals
would miss `mitre_map`. The values are pinned against their evidence:
`extract.capabilities > 8192` (the value that failed), `csf_score >= 106 * 100`,
and `zt_score == 8192`.

A `ReadTimeout` no longer shares the dropped-connection copy that says "you can
retry". It is our 60 s client limit, and a job too large for it fails again on
every retry and is billed again.

## What the review rounds changed

Five adversarial rounds ran before the PR opened. The findings that changed the
code:

- A comment claimed an unlisted purpose raises; it does not. Withdrawn.
- A sizing test rested on an invented 100 tokens per row. Removed, and the range
  is now stated as an estimate.
- Raising the non-streamed adapters' caps broke models whose output ceilings are
  lower. The per-model list failed as described above and was replaced by
  "unchanged".
- The first value pins were too weak (`> 8117` is satisfied by the failing 8192).
- A timeout pattern named a class httpx never raises.

Each code fix was reverted on its own and failed a named test before it was
kept. The prose fixes were checked by re-reading the code.

## Filed from it

- #484: `OpenAIProvider` has no truncation guard.
- #485: raising the non-streamed adapters. This needs per-model ceilings and the
  60 s timeout, and both fail today under the wrong message.
