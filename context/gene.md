# Gene — current status

_Owner: Gene (gene-png). Only Gene's sessions write this file._
_Last updated: 2026-08-08 (post-validation remediation — PRs #22, #23, #24 merged)_

Keep this short and current: your sessions overwrite it freely (it's yours
alone, so it never merge-conflicts). Dave's agents read it at `/pickup` to
know what you have in flight without digging through branches.

## Branch / in flight

**`feat/workflow-steps-all-workspaces`** — rolls the numbered-step pattern from
the ATT&CK workspace out to Tech Debt, CSF and Zero Trust. Risk Register
deliberately left alone (two adjacent actions, no editing surface — steps would
be ceremony).

**Merged tonight:** PR #22 (four Criticals + risk_synthesize batching), PR #23
(ATT&CK empty-capability hard block + intake-queue dropdown), PR #24 (session
refresh race + TTLs + expiry warnings + ATT&CK step ordering). `main` is green.

> ⚠️ **The repo is PUBLIC** (`gene-png/080426SHIELD`). History was audited before
> pushing: `.env` never committed, no `sk-ant-*` key ever in any commit, no
> `*.pem`/`*.key`/`*credentials*` ever tracked. Keep it that way.

## What just happened

A full **end-to-end validation run** against the live local stack, driven by
Playwright, following `Final SHIELD Testing.docx`. All 12 deliverables written
to **`OneDrive/Documents/Kentro/SHIELDv3/Final-Testing-20260807/`** — start at
`REPORT.md`, then `NEW-FINDINGS.md`.

**29 findings, 4 Critical.** Original 22 UX findings: **21 revalidated** — 13
fixed, 7 partially, 1 untestable, **2 regressions** (a fix broke another fix,
twice).

The four Criticals:

1. **N-029** — offline AI guard reports `ready:true` in fixture mode with an env
   key, so banner + Run-AI interception both silently disable. A fixture run
   then **overwrote a client's in-progress ZT answers** (3 of 5 values changed,
   all 5 re-labelled `answer_source='ai'`). Root cause: `_ai_readiness()`
   (`routes/admin.py:778`) never checks `shield_llm_mode`, contradicting its own
   docstring. Draft answers are also unprotected — `answer_source` is stamped
   only at submit.
2. **N-014** — ATT&CK Run AI could never complete. **Fixed and validated in this
   PR** — see below.
3. **N-010** — released client reports state "Total annual cost: $3,368,000" for
   a **$3,608,000** upload with no disclosure that 2 rows were excluded.
   Verified by parsing the actual PDF/XLSX/DOCX.
4. **N-003** — intake step 5 crash. **Fixed in this PR.**

**Phase 4 (Tech Debt) passed cleanly** — reconciles exactly against a key
authored *before* upload. Monthly→annual, alias resolution, dedupe, NULL-vs-zero
cost, bundle non-double-counting, and the unlicensed-ServiceNow trap all correct.

## ATT&CK — N-014 FIXED AND VALIDATED END TO END ✅

The full live run **completed at 20:55**:

| Measure | Result |
|---|---|
| Batches | **26 / 26 COMPLETED, zero failures** |
| Techniques scored | **633 / 633 — zero unscored** |
| Distribution | 387 partial · 116 covered · 85 gap · 45 not_applicable |
| Output tokens | 236,889 (~374/technique) · ≈ **$6** at Opus 5 list rates |
| Wall clock | ~10 min (5 workers × 26 batches @ ~96 s) |

Quality checks on a sampled batch: **no technique IDs outside the supplied
list**, **no tools cited outside the approved capability list**, **no mapping
without a rationale**, rationales prefixed `DRAFT:`. The 633-code allow-list
structurally prevents invented IDs.

PR #22 is now **safe to merge on ATT&CK grounds** (a CI pass on the web
typecheck/lint for the `.tsx` change is still worth having).

**Optional next lever, no longer blocking:** ~374 output tokens per technique is
the cost driver. Bounding rationale length in `_MITRE_MAP_PROMPT` would cut the
~$6 and the ~10 min severalfold.

**Phase 5 of the validation report can now be completed** — it is currently
written as BLOCKED (`PHASE5-ATTACK-ASSESSMENT.md`). Re-run the dataset traps
against the real mappings: ServiceNow (unlicensed module) and the excluded
duplicate must not appear; the six M365 E5 bundle children should map
individually.

## Two bugs the batching work uncovered (both fixed in `9452604`)

- Worker sessions must bind to the **request** session's engine, not module-level
  `SessionLocal` — the latter bypassed the test suite's injected engine. Three
  attack tests passed alone and failed in a full run. **Caught by the existing
  suite, not by review.**
- `engine._ensure_defaults()` set its "already registered" flag **before** the
  import that does the registering — a check-then-set race. Concurrent workers
  returned early to an empty registry (`No AI job registered as 'mitre_map'`).
  Latent since it was written; nothing had called it concurrently before.

## Environment state

- `SHIELD_LLM_MODE=live`, `anthropic/claude-opus-5`. **`.env` holds a real
  Anthropic key that Gene said expires within 24h of 2026-08-07** — confirm it
  did.
- Test client **`UX-E2E-Validation-20260807-1332`**
  (`49d35b66-73a8-41f2-948d-07f306e60142`) — retained deliberately, do not
  delete. Tech Debt service `9e40c1b4-…`, ATT&CK `b347a076-…`,
  ZT `e354c142-…`, CSF `455e09d3-…`.
- Two states left as **evidence**: the ZT assessment holds fixture values from
  the N-029 reproduction, and Tech Debt carries a draft v2 capability list from
  Phase 8 malformed-upload testing. Approved v1 + the released deliverable are
  intact.
- `.playwright-mcp/` is untracked scratch (screenshots, downloads, logs). Not
  ignored — **never commit it**.

## Open concerns — accepted for now, NOT resolved (2026-08-08)

Recorded at Gene's direction: knowingly accepted, to be revisited. Also filed as
a GitHub issue so they are visible outside this file.

1. **The live Anthropic key is an operational and financial risk.** It sits in
   `.env` with `SHIELD_LLM_MODE=live`, so ANY local run — including a stray e2e
   spec — spends real money against it. This has already happened twice: an
   `s30` run burned two failed `risk_synthesize` calls, and an `s5-attack` run
   fired 38 live calls before timing out. **Check the LLM mode before running
   e2e locally.** The key was expected to expire within 24h of 2026-08-07;
   confirm whether it did. Longer term the dev default should be `fixture` with
   live opt-in per command, not the reverse.
2. **AI spend cannot be billed from.** Under-reported by >60% on the validation
   sample: failed calls record NULL tokens (N-019), there are no cache/retry/cost
   columns (C-002), no row is written before dispatch (N-016), and fixture rows
   store character estimates in the same token columns as live rows (N-020).
   **Nobody should invoice a client from this ledger.**
3. **The refresh-rotation grace is a deliberate, narrow security trade** (PR #24).
   A replayed refresh token is accepted for 60s instead of being rejected. It is
   one generation only and time-boxed, and `jwt_refresh_grace_seconds=0` restores
   strict single-use — but it IS a loosening of replay detection, made to stop
   users being logged out mid-task.
4. **`jwt_refresh_ttl_seconds` went 30 min → 24h** in the same PR. Forced by
   arithmetic (a refresh token must outlive the access token it renews), but it
   means a stolen refresh token is useful for a day rather than half an hour. The
   daily forced-reauth ceiling still bounds it.
5. **`shield_idle_timeout_seconds` is dead config** — defined, never read. It
   reads like an enforced 30-minute idle timeout and enforces nothing. Wire it up
   or delete it; right now it is a lie in the settings file.

## Next steps

1. Complete Phase 5 of the validation report — it is written as BLOCKED but real
   mappings now exist; re-check the dataset traps against them.
2. Add the missing e2e spec for intake steps 1→6. Of 41 smoke specs **none**
   walks the wizard to step 5 or submits, which is why the Critical shipped.
3. Run `risk_synthesize` live once. Batching (PR #22) removed the blocker but the
   purpose has still never completed a live generation.
4. Untested and documented as such: ZT/CSF/Risk Register end-to-end, 2 of 5
   Claude purposes live (`csf_score`, `zt_score`), ATT&CK mapping quality at full
   matrix, contrast/200% zoom/print/axe, cross-client authz (needs a second
   tenant).
5. **Live-path tests never run in CI** — `pytest -m live` self-skips without a
   key, so budget/latency/provider defects are invisible to automation. Three of
   five purposes have now been bitten by exactly that. Highest-value gap in the
   test strategy.

## Cost note

Live AI spend across the run: **≈$13** (≈$6 of it the successful ATT&CK run). The ledger under-reports it by >60% —
failed calls record NULL tokens (**N-019**), and one ~15-minute call left no row
at all. Worth fixing before anyone bills from this data.
