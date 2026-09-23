# 2026-09-22 — #471: the Run-AI warning names the server's own cause

Branch `fix/209b-runai-guard-detail`, base `43bfa99`. `tier-1`, `client-reaching`.

## What was wrong

`RunAiGuard.tsx` hardcoded "No API key is loaded — this will generate an offline
response." and `aria-label="No API key loaded"`, and rendered both whenever
`!status.ready`. That is a **five**-cause condition reported with the text of one
cause, and four of the five mean a key IS loaded.

A consultant clicks Run AI, is told the reason is a missing key, knows they
loaded one, dismisses the warning as stale, and proceeds. The run serves
deterministic fixture content into a client deliverable. `routes/admin.py`'s own
comment cites the 2026-08-07 live run where exactly that happened.

`AiStatusBanner.tsx` and `LlmKeyPanel.tsx` already render `status.detail`. The
Management page told the truth; the modal at the point of action did not — and
those two pages are ones you only visit once you already suspect something.

## The brief said four causes; there are five

Measured against `_ai_readiness`: `:819`, `:840`, `:852`, `:860`, `:868`. The one
missing from the brief is `provider not in ("anthropic", "openai", "gemini")` —
"A key is loaded but provider 'X' has no runtime adapter". So it is four of five
that mean a key is loaded, and the test drives five branches.

The brief's line citations for two of them were off by one (`:841`, `:869`). The
quoted strings matched, which is the argument for quoting strings rather than
citing lines.

## Three changes, not one

1. **`{promptFor.detail}`** in place of the hardcoded sentence. `promptFor` is
   already the `AiStatus`, so it was in scope at the line that hardcoded it.
2. **The imperative removed.** "Load a key to run real AI." is false on the
   adapter, SDK and model-id branches. `detail` now carries the remedy that
   applies to the actual cause; the sentence left behind ("Offline (fixture)
   output is deterministic demo content, not analysis of this client's data") is
   true of all five.
3. **`aria-label` names no cause, and stays CONSTANT** — `"AI is not ready to run
   live"`. A screen-reader user heard the same false cause the sighted copy gave.
   Deriving it from `detail` would be more specific and would make the dialog
   unselectable by name: `e2e/helpers/ai.ts` and `e2e/smoke/s34-llm-key.spec.ts`
   both find it that way. Both selectors are updated in this commit, and a test
   pins the constancy so the next person reaching for "derive the aria-label too"
   sees why it is not derived.

`"Load a key"` on the link is deliberately unchanged: it names a control that
exists and works, and does not claim it fixes this cause. Renaming would break
`s34`'s assertion for no correctness gain.

## One existing assertion was pinning the bug

`test_...warns instead of running when no key is loaded` asserted
`/generate an offline response/i` — the tail of the hardcoded sentence. Stated
explicitly per core principle 3: that assertion was pinning the defect, so it is
replaced rather than weakened, by the server's own branch-1 string sourced from
`routes/admin.py`. The fixture's `detail` was also an invented abbreviation ("No
API key is loaded.") and is now the real string, because a fixture written to
what the reader expects cannot express the reader and the server disagreeing.

## What the test establishes

Five branches, five distinct assertions, each expected string copied from
`_ai_readiness` rather than from what the component does with it. One case would
prove nothing — a component that hardcodes whatever string it is handed passes
any single case, which is the mutation-sampling problem one surface over.

Two assertions over the whole set rather than per case, so adding a sixth branch
and forgetting to drive it cannot pass silently: the four "a key is loaded"
branches must render text matching `/key is loaded|key is present/`, and the
accessible name must be identical across all five.

## Verified

| check | result |
| --- | --- |
| `verify-in-worktree.sh vitest` | 753 passed, 62/62 files, 0 never collected |
| `verify-in-worktree.sh tsc` | 0 errors |
| `eslint .` (real invocation — the harness's eslint arm cannot run, #450) | exit 0, 3 pre-existing warnings |
| `prettier@3.9.6 --check` | clean |

**The e2e selector rename is verified by CI's E2E job, not locally.** Worth
knowing why that is safe in one direction and not the other:
`acknowledgeOfflineAi` **fails open** on a selector that matches nothing — it
catches the `waitFor` timeout and returns — so a wrong accessible name would be
silent there. `s34` asserts `toBeVisible()` on the same locator and fails loudly.
That asymmetry is the "a selector that selects nothing passes" shape, and it is
pre-existing.
