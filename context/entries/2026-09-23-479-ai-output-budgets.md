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
`extract.capabilities` failed on `stop_reason=max_tokens` at 00:47 UTC, and its
retry finished at **8117 of 8192**. No live `csf_score` or `zt_score` has ever run
there.

## What changed

| purpose | before | after | basis |
| --- | --- | --- | --- |
| `extract.capabilities` | 8192 (default) | 64000 | measured, above |
| `csf_score` | 8192 (default) | 64000 | **estimate**: 318 rows at 100–575 tokens each. 64000 fits only the low end; batching per tier is the real fix |
| `zt_score` | 8192 (default) | 8192, **chosen** | 3 short fields per capability; raising it would break it on 8192/16384-ceiling models (#485) |

`test_every_registered_job_has_a_chosen_output_budget` walks the registry through
the public `registered_jobs()` / `get_job()`. A grep for `purpose="..."` literals
would miss `mitre_map`. Each new entry was checked red-on-revert, one at a time.

## Corrected by two adversarial rounds, before the PR opened

Round 1:

- A comment claimed that an unlisted purpose raises. It does not; the claim was withdrawn.
- A test named "fits a full working profile" rested on an invented 100 tokens per
  row. The only measured row cost in the repo (~575, `mitre_map`) puts a full
  profile far past any cap, so the test is gone.
- `zt_score` went back from 32000 to a chosen 8192.

Round 2 found that raising a cap **broke working configurations**, and "filed"
was not an answer to that:

- **Ceilings.** README's example OpenAI model (`gpt-4o-mini`, 16384) and
  SMOKE_TEST's live-smoke models (`gpt-4o-mini`, `gemini-1.5-pro` at 8192) would
  have turned a working `csf_score` smoke (364 in / 307 out) into an HTTP 400.
  `output_cap_for` now clamps to the published ceiling of those named families,
  in the OpenAI and generateContent adapters only, and logs
  `llm_output_cap_clamped` when it does. This also stops `mitre_map` and
  `risk_synthesize` sending a 400-inducing cap to those models, which had been
  broken there all along.
- **Timeout copy.** A `ReadTimeout` used to share the dropped-connection copy,
  which says "you can retry". It is our 60 s client limit, and a job too large
  for it fails again on every retry and is billed again. It now has its own copy.
- **Values pinned.** The registry gate proves that an entry exists, not what it
  holds; `extract.capabilities > 8117`, `csf_score > 8192` and `zt_score == 8192`
  are now asserted against their evidence.

Every fix above was checked red-on-revert on its own.

## Filed from it

- #484: `OpenAIProvider` has no truncation guard.
- #485: the general version of the provider problem. Ceilings for families the
  clamp does not name, and the 60 s timeout itself (as distinct from its copy),
  are still open there.
