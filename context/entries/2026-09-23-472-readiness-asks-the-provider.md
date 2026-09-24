# 2026-09-23 — #472: AI readiness asks the provider Run-AI would build

Branch `fix/472-readiness-asks-the-provider`, base `f231b0e`. #472 is `tier-1`,
`client-reaching`.

## What was wrong

`_ai_readiness` decided "configured" by asking whether an API key existed.
Vertex authenticates with ADC and has no key, so a WORKING live Vertex
deployment reported "No API key is loaded — AI steps will generate offline
(fixture) responses. Load a key to enable live AI." The Run-AI guard then
offered "Continue offline", and the run it started went to Google with the
client's data. The printed remedy named a control that cannot work: vertex
has no key, the validator refuses one, and `_build_provider` would refuse a
stored one.

## What changed

- **`routes/admin.py::_ai_readiness`** builds the provider through
  `LLMClient.from_db`, the call every AI route makes, and reports what a
  Run-AI will do as a new `serves` field on `AdminAiStatus`:
  - `live`: the provider will be called;
  - `offline`: canned fixture output;
  - `broken`: the provider build refuses, or the SDK is missing, or the model
    id is a placeholder, so the Run-AI fails.

  `ready` is `serves == "live"`. A build refusal is passed through as
  "Run-AI will fail: <the refusal>", never as offline. That also corrects live
  mode with no key, which used to promise fixtures that nothing serves.
- **Each offline remedy names a control that works for that provider**
  (`_offline_remedy`):
  - "Load a key" appears only where a key can be LOADED here. That is
    `keystore.accepts_runtime_key`, the predicate `live_validate_key` itself
    branches on, and today it covers anthropic alone.
  - openai and gemini take their key from the environment.
  - vertex needs no key, so its remedy is the mode.
  - Wherever the remedy is "set SHIELD_LLM_MODE=live", it comes from the boot
    preflight: `_go_live_advice` runs `live_llm_readiness` on a copy of the
    settings with the mode flipped, and when that would refuse it says why.
    Round 2 of review caught the earlier version telling vertex to go live
    without a project, which stops the api booting.
  - A provider with no live adapter (`azure_openai`, `bedrock`, `local`) is
    told to switch provider. Telling it to go live stops the api booting.

  `llm.has_live_adapter` summarises `_build_provider`'s if-chain, and
  `test_llm_adapters.py` pins that summary against the chain for every member
  of `LLMProvider`, and against the preflight's own provider list.
- **`can_configure` tells the truth.** It was hardcoded `True`. It is now
  `accepts_runtime_key`. Three things show only when it is true: the guard's
  "Load a key" link, the banner's "Load an API key" link, and the key panel's
  paste form. The panel keeps Remove for a stored key either way.
- **The remedy copy is counted.** It lives in two helpers outside
  `_ai_readiness`, so `test_ai_readiness_branch_count.py` now also pins each
  helper's number of returns, and each return has a web-table row.
- **The key panel's removal notice** comes from the status read after the
  removal. It used to say "offline again" even when an environment key kept
  Run-AI live.
- **Web.** `AiStatus.serves`. `RunAiGuard` offers "Continue offline", and the
  sentence describing fixture output, only when `serves` is `offline`. A
  broken configuration is told there is no fallback. `hasAcknowledgedOffline`
  counts an acknowledgement only for `offline`, which covers both of its
  readers: the guard, and Tech Debt's auto-extraction on upload. `LlmKeyPanel`
  says "Not working" rather than "Offline" for `broken`.
- **`test_admin_llm_key.py` now runs in CI.** It had no `unit` marker, so
  `pytest -m unit` deselected all nine of its tests. Five of them failed on any
  machine with an Anthropic key in its environment, because the fixture pinned
  the provider but not the key. The other deselected tests are filed as #500.

## Proof

Red-on-revert, one mutation at a time, each confirmed applied:

| mutation | goes red |
| --- | --- |
| "configured" means "a key exists" (the #472 defect) | the live-vertex, vertex-fixture-mode and live-no-key tests |
| "Load a key" for every provider | the vertex-fixture-mode test |
| a build refusal reported as `offline` | the stored-vertex-key and live-no-key tests |
| "Continue offline" offered for every `serves` | the table test, over every row |
| an acknowledgement that ignores `serves` | the `aiStatus` test and the guard's broken-after-acknowledged test |

The last one first **survived**. `serves` was also part of the
acknowledgement's storage key, so either guard alone was enough and neither
could be tested. The key no longer carries it. The check is still a RATCHET
rather than the only guard: no reachable offline state shares a storage key
with a reachable broken state today, and the check keeps that true if either
changes.

Round 1 of review found these blockers, all fixed:
- the "set it live" remedy for a provider with no adapter;
- "Load a key" offered where the validator refuses a key;
- the removal notice;
- a test that asked `hasAcknowledgedOffline` about a write it refuses before
  looking, and so could not fail. It now reads the storage.

## Residual

The guard acts on the status it read when the page loaded. A key loaded by
another admin afterwards turns an acknowledged offline run into a live one
(#504). ADC is resolved at boot and, since round 2, on the first status read
in fixture mode. Round 3 measured that probe at 3.2-3.9 s with no credentials
(it pings the GCE metadata server), so the answer is cached for the process.
Credentials that change after that still read as they were until a restart.
The copy residuals from round 3 are filed as #511.
