# SPRINT 8 — Prove it in the browser (eyeball-debt burn-down)

_Branch: `feat/browser-proof-sprint-8` (cut from `main` post-#36). Queue:
`.claude/sprint-queue.sprint-8.json` (copy to `.claude/sprint-queue.json` to
launch). Driver: `/loop-sprint-cron` (or execute tasks by hand). Created
2026-07-16 after Sprint 7 (PR #36, `v3.4.0`) merged._

_Plan reviewed by OpenAI Codex (v0.144.5, read-only, 2026-07-16) — verdict
"ship-with-changes"; all findings folded in: the T1 guard-placement blocker,
the explicit pytest re-contract, the MFA task split (T4/T5), mandatory
recovery-code coverage, subject-aware MailHog polling, the `/documents`
empty-state addition, and the task ordering below._

## Why this sprint exists

Sprint 6/7 made the flows real, but a block of SMOKE_TEST items is still
proven only by unit tests or by nobody: the release notification has never
been SEEN in MailHog by a committed spec (§29), the MFA enrollment/sign-in UI
and the verify/forgot/reset pages have zero browser coverage (Dave was going
to walk them by hand), `/admin/health` and the `/documents` empty state are
human-runtime checks, and the tech-debt extract route still mints unbounded
versions on every POST — the same defect CSF fixed in Sprint 2 T7 and
attack/zt inherited in Sprint 3 T1 (`context/dave.md`'s note that all three
still share it was stale; only tech-debt remains, and its route runs a real
LLM extraction before minting, so hammering "extract" is also a surprise-cost
bug, not just a version-spam bug).

The theme is the honesty convention itself: convert human-eyeball debt into
green committed specs, and retire Dave's manual MFA walkthrough entirely.

## Sprint goal

Every auth surface (MFA enrollment, TOTP sign-in, recovery-code sign-in,
verify-email, forgot/reset password), the release notification, `/admin/health`,
and the `/documents` empty state are proven by committed Playwright specs; a
double-POST to the tech-debt extract route reuses the open draft instead of
burning a second LLM call and minting a new version.

Version at close: **`3.4.1`** (patch: regression/browser proof + one
backward-compatible idempotency fix, no new user-facing surface). Version is
tag/CHANGELOG-level only — package manifests are NOT touched.

## Prerequisites / launch checklist

1. Merge this planning PR.
2. `git checkout -b feat/browser-proof-sprint-8 main` BEFORE the first fire.
3. Archive the old runtime queue if one exists on your box (fresh clones have
   none), then COPY `.claude/sprint-queue.sprint-8.json` to
   `.claude/sprint-queue.json`; set `working_dir` + `expected_gh_user` for
   YOUR box; confirm the `gates` array matches your environment (six gates
   unchanged from Sprint 7).
4. The human dev launching this sprint runs `/loop-sprint-cron` themselves —
   agents do NOT start the loop.
5. No live-AI or cloud credentials needed this sprint — everything runs
   against the fixture-mode dev stack + MailHog.

## Environment facts the loop must know

All CLAUDE.md gotchas hold, plus:

- Email delivery is ON by default in dev/CI compose since Sprint 7 T3
  (MailHog SMTP :1025, UI/API :8025) — the new mail specs rely on it.
  `SHIELD_AUTH_REQUIRE_EMAIL_VERIFY` and `SHIELD_AUTH_REQUIRE_MFA` stay
  **false** (flipping either breaks existing e2e sign-ins).
- MailHog is shared, per-run-disposable state: every mail assertion must use a
  unique timestamped recipient AND match on expected subject (registration
  also emails the same recipient — first-message-wins races; bit the s21
  design review).
- T4 adds a TOTP dependency to `e2e/package.json` → run `npm ci` (or
  `npm install`) inside `e2e/` on the HOST before running the new specs. The
  e2e harness is host-run; no container rebuild involved.
- Web auth is Auth.js v5: the MFA sign-in signal is `signIn(...).code ===
  "mfa_required"`, not `.error` (Sprint 7 T5); `SignInForm.tsx` already
  handles the second-step code field — specs drive the UI, they do not call
  `signIn()` directly.
- After ANY `apps/web` source edit: `docker compose up -d --force-recreate
  web` before e2e (T1 is api-only; T2–T6 should need no web source changes —
  if one does, the dance applies).
- Playwright traps (recurring): `getByRole` name matching is SUBSTRING
  (`exact: true` near siblings); `click()` + `waitForResponse` on auto-save
  controls; assert post-action state after `page.reload()` where StrictMode
  double-loads; spec-created users need unique timestamped emails.

## Tasks

### T0 — Shared MailHog helper (`e2e/helpers/mailhog.ts`)

- Extract the inline MailHog reader from `s21-email-verify.spec.ts:19-52`
  (`MAILHOG_API`, `fetchLatestMessage`, `extractToken`) into
  `e2e/helpers/mailhog.ts` beside `auth.ts`/`baseUrl.ts`/`ids.ts`.
- Upgrade the search: poll by recipient **plus expected subject** (Codex
  review finding — registration also emails the target address, so
  "latest for recipient" can select the wrong message). Keep the
  quoted-printable collapse + `token=` regex in `extractToken` (T3 needs it;
  T2 does not).
- s21 consumes the helper; zero behavior change; full e2e suite stays green.

### T1 — Tech-debt extract draft-exists guard (idempotent 200, no re-extract)

- In `extract_capability_list` (`apps/api/app/routes/tech_debt.py:144-233`):
  look up the latest `CapabilityList` **after** service/artifact validation
  but **BEFORE** `extract_capabilities()` at line 168 — guarding at the old
  mint site (line 194) would still fire the surprise LLM call (Codex blocker).
- If the latest list status is `DRAFT`: log `techdebt_reused_open_draft`
  (id/version/service, module prefix), return the existing draft untouched
  with idempotent **200** via a `Response` param overriding the declared 201 —
  byte-for-byte the CSF shape (`csf.py:366-390`). NO re-extraction, NO
  clear-and-repopulate: clearing would destroy consultant edits/locks
  (`tech_debt.py:264-328` supports them), and a double-click must never be a
  destructive LLM operation.
- **Deliberate test re-contract (saying it out loud per the TDD rule):**
  `test_extract_versions_subsequent_lists`
  (`tests/unit/test_tech_debt_routes.py:281`) currently proves consecutive
  POSTs mint v1→v2 — that contract is superseded by this task, matching the
  other three services. Rewrite it to prove versioning across the
  APPROVED/RELEASED boundary instead.
- New contract tests (TDD-first, watch them fail): (1) second POST while a
  draft is open → 200, same list id/version/items; (2) the LLM provider is
  invoked exactly once and no second `llm_calls` row exists; (3) no second
  `capability_list.extracted` audit row; (4) latest list APPROVED/RELEASED →
  a new extraction mints the next version with 201; (5) a POST with a
  **different** `artifact_id` while a draft is open still returns the existing
  draft (documented contract — the 200 status + log make the reuse
  observable; an explicit "replace/re-extract" affordance is a future
  candidate, out of scope).
- No new D-number: this applies the existing CSF/attack/zt pattern. Fix the
  stale mint-route claim in `context/dave.md` (T7 carries the doc edit).

### T2 — `s22-release-notify.spec.ts` (SMOKE §29)

- Create an **isolated tenant + unique-email client user** in-spec (the
  Sprint-5 s17 pattern) rather than reusing the shared seed — the point is to
  prove recipient selection for real, not just that some mail exists.
- Finalize + release a CSF deliverable (reuse the `releaseCsfDeliverable`
  helper shape from `s18-home.spec.ts:84`; the finalize sequence reference is
  `s17-documents.spec.ts:134`).
- Assert via the T0 helper that the notification lands in MailHog for that
  client user: recipient + subject `"Your {service_label} deliverable is
  ready"` (`apps/api/app/email/sender.py:101`), body carries the
  `/documents` link.
- Checks SMOKE §29 (currently unit-proven only, box explicitly unchecked).
  Depends: T0.

### T3 — `s23-auth-pages.spec.ts` (verify / forgot / reset pages)

- Browser-drive the three pages
  (`apps/web/src/app/{verify-email,forgot-password,reset-password}/page.tsx`):
  register a unique-email user → pull the verification token from MailHog
  (`extractToken`) → land on `/verify-email` with the token and assert the
  success state; then request a reset from `/forgot-password`, pull that
  token, complete `/reset-password`, and **sign in with the new password**.
- s21 stays untouched as the API-path proof; this spec proves the PAGES —
  converts the §24/§25 "human eyeball the web pages" annotations to
  spec-backed checks. Depends: T0.

### T4 — `s24-mfa.spec.ts` part A: enrollment + TOTP sign-in

- Add a TOTP generator dep to `e2e/package.json` (`otpauth` or equivalent —
  keeps Base32/clock-window details out of the spec). Real code generation is
  unavoidable: enrollment confirmation itself requires a valid TOTP
  (`MfaEnrollment.tsx:39-78`), so no recovery-only shortcut exists.
- Fresh spec-created user → `/account` → enroll: capture the displayed secret
  (`MfaEnrollment.tsx:126`), confirm with a generated code, assert the
  recovery codes are displayed once (capture them for T5's pattern).
- Sign out → sign in driving the UI's TOTP second step (`SignInForm.tsx`,
  Auth.js v5 `result.code` signal) with a freshly generated code → assert the
  authenticated landing.
- `SHIELD_AUTH_REQUIRE_MFA` stays default-off (enrollment is per-user
  opt-in); the spec's own user keeps the serialized shared-DB suite
  untouched.

### T5 — `s24-mfa.spec.ts` part B: recovery-code sign-in (single-use)

- Self-contained test with its OWN fresh user (no cross-test state): enroll
  via the same UI flow, capture the recovery codes, sign out.
- Sign in using one recovery code in the TOTP field (the input accepts it —
  `SignInForm.tsx:104-119`, placeholder "6-digit code or recovery code" at
  `:114`) → assert success. Sign out, attempt the SAME code again → assert
  rejection (single-use consumed).
- Split from T4 deliberately (Codex review): enrollment/TOTP and
  recovery-code redemption are distinct failure seams; each task stays
  independently green. Together T4+T5 retire Dave's manual MFA walkthrough
  (SMOKE MFA eyeball item).

### T6 — Demo/ops strays: `s25-admin-health.spec.ts` + `/documents` empty state

- `s25-admin-health.spec.ts`: sign in as admin, drive `/admin/health` against
  the healthy dev stack, assert the full-matrix all-green operator view —
  converts the SMOKE human-runtime check (§ "Eyeball `/admin/health`").
- `/documents` empty state (SMOKE_TEST.md:228, the no-dead-ends rule): in the
  s17 isolated tenant, assert the empty state renders BEFORE the release step
  — the tenant already exists there; near-zero marginal cost (Codex-found
  cheap item). Lands as an added assertion in `s17-documents.spec.ts`.

### T7 — Wrap-up

- SMOKE_TEST: check §29 (s22), the verify/forgot/reset UI eyeball item (s23),
  the MFA UI eyeball item (s24), `/admin/health` (s25), `/documents` empty
  state (s17) — each annotated with its spec filename, honesty convention.
  **Eligibility note in the PR body:** unit-proven backend-invariant boxes
  (§16 release deny paths, §20 preview internals, §21 audit filters) and the
  end-of-file sign-off boxes stay UNCHECKED — nothing this sprint proves them
  in a browser.
- CHANGELOG `[3.4.1]` per-task entries with commits; BUILD_REPORT sync (gate
  results at HEAD, e2e spec count 21 → 25 files).
- `CONTEXT.md` overwritten with the end-of-sprint snapshot; the LAUNCHING
  dev's own `context/<name>.md` refreshed (owner-only rule — never write
  another dev's context file).
- Full exit gate set (all six) + full e2e.

## Definition of done

- A committed green spec exists for: release notification visible in MailHog,
  verify/forgot/reset pages driven in a browser, MFA enrollment + TOTP
  sign-in, recovery-code sign-in + single-use rejection, `/admin/health`
  all-green, `/documents` empty state. Dave's manual MFA walkthrough is
  retired.
- Double-POSTing tech-debt extract while a draft is open returns the same
  draft with 200, exactly one LLM call and one audit row; the
  APPROVED/RELEASED path still mints the next version.
- SMOKE_TEST boxes checked only with spec filenames; ineligible boxes left
  unchecked with the eligibility note in the PR.
- No credential committed; every commit conventional and task-scoped;
  CONTEXT.md snapshot written.

## Explicitly out of scope (needs-Dave / later)

- **Loop launch** — the human dev at the keyboard starts `/loop-sprint-cron`;
  agents never do.
- Keycloak SSO / Auth.js OIDC cutover (seam stays dormant).
- demo-reset / hosted-demo automation (destructive `down -v`; stays a manual
  checklist item).
- §10 export eyeballs (human by definition).
- ESLint 10 + the `postcss` moderate (upstream-blocked).
- Cloud deploy / terraform / DR runbooks; FedRAMP LLM connector;
  `azure_openai`/`bedrock`/`local` adapters (loud not-implemented).
- A tech-debt "replace/re-extract draft" UI affordance (the long-term right
  shape for intentional re-extraction — future sprint candidate).
