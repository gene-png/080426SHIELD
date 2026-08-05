# Gene — current status

_Owner: Gene (gene-png). Only Gene's sessions write this file._
_Last updated: 2026-08-04_

Keep this short and current: your sessions overwrite it freely (it's yours
alone, so it never merge-conflicts). Dave's agents read it at `/pickup` to
know what you have in flight without digging through branches.

## Branch / in flight

- `fix/seven-issue-pass` — seven reported issues, fixed in four phases, PR open
  against `main` targeting `v3.8.0`. Two additive migrations (0033
  `client.archived_at`, 0034 `llm_credentials`), new decisions D-036/D-037/D-038,
  six new e2e specs (`s31`–`s36`).
  - **Issues 1 / 5 / 6** — navigation dead ends: `/home` service cards were
    unlinked, `/admin/active` was a stub, and the skip link's focus ring was
    cancelled by `outline-hidden`.
  - **Issues 3 / 7** — soft client archive + user deactivate/reactivate, and
    `/admin/queue` became an index of organizations instead of opening onto
    whichever tenant was created last.
  - **Issue 2** — runtime provider API-key management (validate-then-store,
    Fernet at rest, DB beats env), plus the offline warning on every admin page
    and a Run-AI guard.
  - **Issue 4** — nothing in the product could release a deliverable, so the
    D-035 client dashboards were unreachable for every client. Fixed, plus an
    admin pre-release preview through the same builder.

## Next steps

1. PR review + merge, then tag `v3.8.0`.
2. Open follow-ups (also listed in the PR body):
   - `s34-llm-key`'s Run-AI-guard test self-skips when the seeded ATT&CK
     assessment is already released (Run AI renders disabled), so whether the
     browser exercises the dialog depends on DB state. A spec that seeds its own
     unreleased service would make it unconditional. Note this skip is what hid
     the fail-open race until the first full-suite run — treat a
     conditionally-skipping spec as untested, not as passing.
   - Key validation has a real provider probe for `anthropic` only. openai /
     gemini / vertex refuse with an explicit "not implemented for this provider"
     rather than pretending to validate — worth closing.
   - SMOKE §36's live-key line still needs a human with a real key.
3. `release_deliverable()` still never flips the per-service assessment to
   `RELEASED` (noted in D-035, unchanged here). Consistency cleanup, not urgent.

## Notes for Dave

- `/auth/login` never checked `User.is_active` before this branch — refresh,
  MFA-verify and password-reset all did. If you have anything that assumed
  deactivation blocked sign-in, it did not until now.
- `dashboardPathFor()` (`apps/web/src/lib/dashboards/routes.ts`) is now the single
  source of truth for "where does this service kind go" — `/home` and
  `/documents` both read it. Add new service kinds there, not in a local switch.
- `jsonRequest`'s error path in the six `lib/*/client.ts` wrappers used to read
  the response body twice, which threw and masked the real status. Fixed in all
  six; if you touch one, keep the single read.
- My box runs web on `:3000` (canonical), not the `:3001` your CONTEXT machine
  notes describe.
