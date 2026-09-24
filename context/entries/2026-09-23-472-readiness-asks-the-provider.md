# 2026-09-23 — #472: AI readiness asks the provider Run-AI would build

Branch `fix/472-readiness-asks-the-provider`, base `f231b0e`. #472 is `tier-1`,
`client-reaching`.

## What was wrong

`_ai_readiness` decided "configured" by asking whether an API key existed.
Vertex authenticates with ADC and has no key, so a WORKING live Vertex
deployment reported "No API key is loaded — AI steps will generate offline
(fixture) responses. Load a key to enable live AI." The Run-AI guard then
offered "Continue offline", and the run it started went to Google with the
client's data. Following the printed remedy instead broke the deployment,
because `_build_provider` refuses a stored key for vertex.

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
- **"Load a key" is prescribed only for a provider that takes one**
  (`keystore.accepts_api_key`). For vertex in fixture mode the remedy is the
  mode.
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
could be tested. The key no longer carries it, so the explicit check is the one
guard.

## Residual

The guard acts on the status it read when the page loaded. A key loaded by
another admin afterwards turns an acknowledged offline run into a live one
(#504). The ADC check is the boot preflight's alone: credentials that stop
resolving after boot still read `live`.
