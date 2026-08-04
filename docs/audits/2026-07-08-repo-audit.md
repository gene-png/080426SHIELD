# SHIELD Repository Audit — Sprint 3 Planning Input

_Performed 2026-07-08 by a Claude (Fable 5) deep-audit agent at working tree
`f771f85` (equivalent to `main` post-PR #19 for all engine/route logic).
Commissioned by David to verify: (1) what the product is supposed to do,
(2) documentation accuracy, (3) code-vs-design conformance, (4) gaps and new
functionality. All findings verified statically with file:line evidence.
This document seeded `SPRINT_3.md`._

---

## 1. What it is supposed to do

**Product scope** (Master Spec `reference-docs/SHIELDv2_Master_Spec.txt` + DECISIONS D-001..D-019): SHIELD runs the full lifecycle of a Kentro consulting engagement — self-signup → service-driven intake → consultant-driven, AI-assisted analysis → executive deliverables (PDF/XLSX/DOCX) — across four services: **Tech Debt Review** (spec §2.1), **Zero Trust** (CISA ZTMM 2.0, 5 pillars + 3 cross-cutting, 4 maturity levels; DoD ZTRA, 7 pillars — spec §9), **NIST CSF 2.0** full 10-step Playbook (spec §8), **MITRE ATT&CK coverage** over the _full_ Enterprise matrix (D-007, flipped from the spec's curated-subset recommendation). A **Risk Register** (5×5 NIST 800-30) synthesized from the four services is _post-spec_ scope from the v2 Work Order (Part E) — it appears nowhere in the Master Spec.

**Deterministic-scoring contracts** the code must honor:

- **CSF (spec §8):** five dimensions 0–2 each → total 0–10 → maturity L1–L5 (0-2/3-5/6-7/8-9/10); evidence cap (no evidence ⇒ Implementation ≤ 1 AND level ≤ 2); weighted-floor Enterprise roll-up, six ordered rules, Rule 2 (Core+Primary strict floor) overrides Rule 5 (Supporting/Supplemental exception); gap = current < target; priority P1 (Core AND HIGH-tier AND multi-system) / P2 (Core OR HIGH) / P3.
- **Risk:** score = (li+1)×(ii+1); tier bands ≥15 High / ≥9 Medium / ≥4 Low, with Critical overrides (High-or-VH × Catastrophic; VH × Major+); **tier is never AI-set**.
- **ZT:** stage clamps CISA 1–4, DoD 1–3; pillar roll-ups, gap = current < target, weighted prioritization, 12-month roadmap — all in code.
- **"AI suggests, code computes"** (spec §4.4/§12): LLM drafts values/narrative only, through one redacting egress module, with `llm_calls` audit rows; redaction is the **primary** security control (non-FedRAMP provider risk explicitly accepted).
- **Roles/auth:** spec defines three roles, but Work Order A3 collapsed reviewer into admin; D-004 self-registration (first registrant bootstraps admin); D-015 superseded the spec's single-tenant posture with shared-DB multi-tenancy (`client_id` on every business table, X-Client-Id switching, 404-on-mismatch); D-016 typed `{reason, message}` errors; MFA/email-verify deferred behind flags (spec §4.5).
- **Provenance gap [GAP]:** the "v2 Developer Work Order (Parts A–F)" that legitimately supersedes large chunks of the Master Spec (reviewer removal A3, admin-only deliverables A1, DoD 3-level model A4, Risk Register E, multi-tenancy) is **not in the repo** — `reference-docs/` has only the original spec. The de facto spec is reconstructible only from code comments and D-numbers.

---

## 2. Is the documentation accurate

### Materially wrong (highest impact first)

- **[DOC-DRIFT] `docs/architecture.md` is badly stale — the single worst doc.**
  - Line 7 & 68: "SHIELD is a single-tenant web platform… there is **no tenant-id column** on tables… multi-tenancy is explicitly out of scope" — flatly contradicted by D-015 (DECISIONS.md:112) and the code (`client_id` on every business model, `app/dependencies.py:89` `current_client`, migration `0013_multi_tenant_client_id.py`).
  - Lines 13, 43–49, 59, 63: Celery worker (`apps/worker`), "Redis (Celery + cache)", "Celery 5" — the worker was removed in Part F (DECISIONS.md:134-141); AI runs synchronously in `api`; Redis has no consumer.
  - Line 72: audit table named `audit_events` — the real table is `audit_entries` (`app/models/audit_entry.py`, migration `0001_initial_schema.py:91`).
  - Line 77: AI flow shows `redactor.unredact(text)` on the return path — no unredact function exists anywhere in `app/ai/redact.py`.
- **[DOC-DRIFT] `README.md:3`** — "Single-tenant per deployment" contradicts D-015/BUILD_REPORT ("Multi-tenant", BUILD_REPORT.md:55).
- **[DOC-DRIFT] `README.md:130` + `docs/runbooks/`** — README promises "incident, backup, key rotation, DR" runbooks; **`docs/runbooks/` is empty**. There is no backup/restore procedure anywhere.
- **[DOC-DRIFT] `README.md:29-31`** — `infra/terraform/` listed as "IaC for AWS GovCloud / Azure Government" but the directory is **empty**.
- **[DOC-DRIFT] `README.md:137`** — lists "daily forced re-auth" and "30-minute idle timeout" as active compensating controls for deferred MFA. Neither is enforced in code (see §3d). BUILD_REPORT.md:110 (A07 row) repeats the claim.
- **[DOC-DRIFT] `docs/operations.md:15-16,39` and `docs/development.md:27`** — still describe a `worker` service / Celery / `docker compose up -d --build api worker`; operations.md also promises Prometheus metrics that nothing implements.
- **[DOC-DRIFT] Test-count claims** — BUILD_REPORT.md:68/93, CONTEXT.md:23-24, CHANGELOG `[3.0.1]` all say "16 spec files / **32** tests"; `playwright test --list` reports **"Total: 34 tests in 16 files"** (verified live).
- **[DOC-DRIFT] `CHANGELOG.md`** — two different releases both headed `[3.0.0]` (line 63 "Sprint 1 · smoke sweep" and line 80 "v2 work order Parts A–F").
- **[DOC-DRIFT] `README.md:110-113`** — advertises `pytest -m integration` and `docker compose exec web pnpm test`; neither exists as a real gate. Line 117-118 says "14 spec files" — it's 16.
- **[DOC-DRIFT] `DECISIONS.md` duplicate D-015** (lines 112 and 134). D-006 (line 44) still describes a reviewer-approval + release-to-client flow that Work Order A1 removed (`app/models/deliverable.py:7-8`: "there is no client release path"); no superseding D-entry records that.
- **[DOC-DRIFT] Master Spec "108 subcategories"** (spec lines 84, 1301, 1413) — the catalog implements **106** (`app/csf/catalog.py:1`), matching NIST CSF 2.0 Final; the spec's own count is wrong. Never recorded against the Master Spec.

### Accurate (spot-verified) — [VERIFIED]

- **CLAUDE.md**: commands, gotchas, port and PATH facts all check out.
- **CONTEXT.md**: task→commit table matches `git log`; deferred-items list matches code reality.
- **SMOKE_TEST.md**: honesty convention holds. Spot-verified: §1 → `e2e/smoke/s0-home.spec.ts:42-51` (no "reviewer", correct ATT&CK name); §7 → `s7-csf-playbook.spec.ts:157` (exactly 106 enterprise rows) and :214-222 (no-evidence cap math); §13's `EnsureActiveClient` caveat accurate. Unchecked boxes (§10, §14) genuinely need a human.
- **e2e/README.md**: layout, helpers, port resolution, bring-up all match disk.
- **BUILD_REPORT.md**: accurate except the two items flagged above (test count; A07 overclaim).

---

## 3. Is the code doing what it's designed to do

### (a) Deterministic engines

- **CSF Playbook — [VERIFIED]** (`apps/api/app/csf/playbook.py`). Dimension clamp 0–2 (:39-49), total 0–10 (:52), maturity bands per spec (:58-69), evidence cap both clauses (:80-102), weighted-floor rules 1–6 in spec order with Rule 2 > Rule 5 (:111-169), gap and P1/P2/P3 (:172-188). Rules 2/5 inputs are real since Sprint 2: IG Core/Alignment metadata in `app/csf/catalog.py:922+` threaded at `app/routes/csf.py:1012-1020`. Interpretation note: spec Rule 2's "any tier has a gap" is implemented as "tier scores diverge" (playbook.py:144-146) — defensible; confirm against `Step_3_1_Gap_Analysis_Methodology.docx`.
- **Risk engine — [VERIFIED]** (`apps/api/app/risk/engine.py`). Score formula (:77-81), Critical overrides + band cutoffs (:84-100) exact; tier is code-derived (`app/routes/risk.py:234-235`) and AI-cited techniques/controls are filtered against the client's own catalogs (:236-237).
- **ZT scoring — [VERIFIED]** (`apps/api/app/zt/scoring.py`). `_validated` clamps 1..level_count — CISA 4, DoD 3 (:122-134, `app/zt/maturity.py:1-13`); run-AI independently re-clamps (`app/routes/zt.py:383-388`). **Caveat [GAP]:** pillar weights (scoring.py:38-56) and the even-spread roadmap (:297-321) are Kentro-invented heuristics, not spec math — least-documented "deterministic" numbers in the platform. DoD is a 50-capability 3-stage model vs the spec's 152-activity model (`app/zt/catalog.py:11-13`, documented v1 baseline).

### (b) "AI suggests, code computes" + single redacting egress

- **Single egress — [VERIFIED].** Only provider-SDK import: `from anthropic import Anthropic` in `app/ai/llm.py:118`; no other egress. All five AI features route through `run_job` (`app/ai/engine.py:83`) → `LLMClient.invoke`; call sites `tech_debt/extract.py:186`, `routes/attack.py:488`, `routes/csf.py:1099`, `routes/risk.py:206`, `routes/zt.py:391`.
- **Redaction — [VERIFIED].** `invoke` redacts before any provider call (`llm.py:200-205`), writes the `llm_calls` row `status=running` before egress (:211-224), records redacted counts only, boundary `except` logs + re-raises (:233-244).
- **No AI-computed scoring — [VERIFIED]** on all apply paths (CSF clamps + skips locked rows; ZT re-clamps; ATT&CK validates cited tools; risk derives tier; prompts forbid computing totals, `app/ai/jobs.py:49-50,66-67,84-85,105-106`).
- **[CODE-DRIFT — CRITICAL] CSF live-mode prompt/parser schema mismatch.** `_CSF_SCORE_PROMPT` instructs `{"subcategories": [...]}` (`app/ai/jobs.py:50-53`) but the route parses `data.get("scores", [])` keyed `tier`+`subcategory_code` (`app/routes/csf.py:1113-1116`) — the **fixture's** shape (`app/ai/fixtures.py:180-192`). In `SHIELD_LLM_MODE=live` a schema-compliant Claude response is **silently discarded** — Run AI reports zero changes, no error (FAIL-LOUDLY violation). Tests register `"scores"`-shaped fixtures (`tests/unit/test_csf_run_ai.py:85,114,139`) so they cannot catch it. ZT/ATT&CK/risk prompts match their parsers.
- **[CODE-DRIFT] CSF live-mode has no grounding.** `csf_score` payload is only `{"tiers": [...], "subcategories": [...]}` (`routes/csf.py:1103-1106`) — no interview answers/evidence — while the prompt claims they're supplied (`jobs.py:42-43`). ZT sends answers+notes (`routes/zt.py:398-400`). Live CSF suggestions would be ungrounded. Both findings surface the moment SMOKE_TEST §14 is attempted.
- **Minor:** `llm_calls` lacks `client_id` (only nullable `service_id`, `app/models/llm_call.py:45`); risk-synthesis passes no `service_id` (`routes/risk.py:206-216`).

### (c) Multi-tenant isolation (D-015) — [VERIFIED]

`app/tenant.py` 404-on-mismatch for Service/Artifact/CSF/ZT/Attack/Deliverable (:34-127). `current_client` (`app/dependencies.py:89-137`) pins client users, requires X-Client-Id for platform users. Sampled routes all take the dependency (csf/zt/attack, `routes/messages.py:60,92,130`, `routes/artifacts.py:74-190`). Web forwards the cookie server-side only (`apps/web/src/lib/api.ts:54-69`). Covered by `test_multi_tenant_isolation.py`, `test_new_surface_authz.py`, `s13-isolation.spec.ts`.

### (d) Typed errors + fail-loudly

- **[VERIFIED]** Global handlers (`app/exceptions.py:25-42`) correlation-ID-only 500s + D-016 pass-through; fixture-miss → typed 503; ~30 `except` sites surveyed, no bare except / swallow-and-default in API code; web `catch {}` sites commented and justified (`lib/api.ts:62,86`).
- **[CODE-DRIFT]** The CSF live-mode silent no-op (above) is the one real breach found.
- **Minor:** `RequestValidationError` handler returns raw `exc.errors()` in `details` (`exceptions.py:45-56`) — internals leak on non-register 422 surfaces.

### (e) Auth/roles (D-004/D-005/D-006)

- **[VERIFIED]** D-004 register flow (`routes/auth.py:10-14,175-178`); lockout 10-in-15-min (`auth.py:98-118`); constant-time dummy-hash (:55); Argon2id.
- **[VERIFIED]** Reviewer removal (A3) functionally complete: `UserRole` = {ADMIN, CLIENT} (`app/models/user.py:25-28`); zero "reviewer" in `apps/web/src`; s0 pins the copy. **[DOC-DRIFT]** stale reviewer references persist in backend docstrings/OpenAPI: `app/dependencies.py:9,97,115`, `app/security/jwt.py:12`, `app/schemas/auth.py:52`, `app/routes/admin.py:9,144,197` (visible at `/docs`), `app/routes/intake.py:15`, ~10 test files.
- **[CODE-DRIFT] D-005/D-006 are dead letters:** no reviewer; deliverables admin-only, no release flow (`app/models/deliverable.py:7-8`; migration `0015_drop_released_to_client_at.py`). Supersession never recorded in DECISIONS.
- **[CODE-DRIFT] Compensating-control drift:** `shield_idle_timeout_seconds`/`shield_forced_reauth_seconds` (`app/config.py:70-71`) referenced nowhere; `/auth/refresh` (`routes/auth.py:315-333`) re-issues indefinitely, no rotation/revocation — "daily forced re-auth" (README:137, BUILD_REPORT A07) does not exist. (Idle timeout ≈ the 30-min refresh TTL — that half is defensible.)
- **[CODE-DRIFT] Dead MFA flags:** `shield_auth_require_mfa`/`shield_auth_require_email_verify` (`config.py:58-59`) read by nothing; spec §4.5's flag-flip contract unimplemented; enabling them in prod silently does nothing.
- **UNTESTABLE-STATICALLY:** Keycloak realm-export flow semantics for disabled MFA/email-verify (needs a running Keycloak).

---

## 4. Gaps and new functionality

### (a) Spec-promised, not implemented

- **[GAP]** Deliverable release-to-client flow + client deliverable surface (D-006, spec §6.7). Client page inventory 10 vs spec's 14; missing: `/home` executive dashboard with the **cross-service value loop** (spec §2.5/§6.4 — "the highest-value page in the platform"), `/documents`, `/team` + invitations (spec §6.9, `user_invitations` never built), `/help`.
- **[GAP]** Admin surfaces absent (spec §5.2): `/admin/audit`, `/admin/activity`, `/admin/documents`, `/admin/deliverables`, `/admin/settings`. Consultation-request intake path (spec §6.2 I1B): `service_requests` model exists, no wizard short-circuit.
- **[GAP]** i18n (D-009): no `next-intl`; strings hardcoded — "zero-rewrite" promise is currently a rewrite.
- **[GAP]** MFA/email-verify flag plumbing worse than "deferred": flags exist and do nothing.
- **[GAP]** DoD ZTRA catalog 50 of 152 activities (`app/zt/catalog.py:12-13`).
- **[GAP]** §15.5 filename convention: four service routes comply via `deliverable_filename()`; **CSF Playbook 5-file export** (`routes/csf.py:1202,1211-1259`) and **Risk Register** (`routes/risk.py:332-356`) do not.
- **[GAP]** Redactor "first-call review state" (spec §12 preview/approve before first egress per engagement) not implemented.

### (b) Engineering gaps

Known, re-confirmed: unbounded mint on `POST /attack/.../assessments` (`routes/attack.py:243`, pre-seeds ~600 rows/version) and `POST /zt/.../assessments` (`routes/zt.py:471`, ~87 rows) — T7 pattern copy-ready from `routes/csf.py:364-381`; Next 14 line with D-018 majors deferred; empty `infra/terraform/`; duplicate D-015; FedRAMP LLM connector absent (only `anthropic` implemented; `_build_provider` fails loudly for the other five, `llm.py:160-168`).

Newly found:

- **[GAP] No backup/restore/DR anything** — `docs/runbooks/` empty, no pg_dump/MinIO snapshot tooling, no restore test. Largest operational hole for a FedRAMP-target platform.
- **[GAP] Session hardening** — no refresh rotation/revocation (logout is audit-only, `auth.py:336-353`), no forced re-auth.
- **[GAP] No rate limiting** anywhere; Redis idle; `/auth/login`+`/auth/register` unthrottled beyond per-account lockout.
- **[GAP] ATT&CK scale posture:** full-matrix (D-007) means ~600 rows serialized per grid GET, ~600 written per mint, no pagination — most realistic DB-bloat/latency path; measure before adding tenants.
- **[GAP] Error observability:** good structlog+correlation IDs, but nothing ships them (no Sentry/OTel/metrics endpoint); operations.md promises Prometheus that doesn't exist.
- **[GAP] Audit-log coverage:** 42 `audit()` sites but no read surface; `llm_calls` lacks tenant attribution.

### (c) New functionality suggestions (grounded)

1. **[SUGGESTION] Client-facing deliverable release + executive home** — engines/exporters/`Deliverable` model + versioning all exist; needs re-added `released_to_client_at`, release route + audit, client page. Feasibility: **M**.
2. **[SUGGESTION] Cross-service value-loop synthesis card** (spec §2.5): Tech Debt savings (`tech_debt/overlap.py` computes totals) × ZT gaps × ATT&CK uncovered × CSF gaps — one deterministic `value_loop.py` mirroring `risk/engine.py` + a dashboard card. Feasibility: **M**.
3. **[SUGGESTION] Redacted-payload preview & approve gate** before first live egress per service (spec §12): `redact_payload` is pure; `POST /ai/preview` + approval flag. Feasibility: **S/M**.
4. **[SUGGESTION] Admin audit-log viewer** (`/admin/audit`): rich append-only `audit_entries` data, zero UI. Feasibility: **S**.
5. **[SUGGESTION] POA&M / action-plan export for CSF gaps** (spec §8 Step 10): `gap_priority` exists; owner/deadline/success-criteria/POA&M-ref fields don't. Feasibility: **M**.
6. **[SUGGESTION] `llm_calls` tenant attribution + AI-usage report**: additive `client_id` + per-tenant usage/redaction summary. Feasibility: **S**.

---

## Sprint 3 candidate list (ranked)

| #   | What                                                                                                    | Why                                                            | Size | Loop-able                  |
| --- | ------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- | ---- | -------------------------- |
| 1   | **Fix CSF live-mode Run-AI** (prompt/parser schema + payload grounding + live-shape contract test)      | Live mode silently broken for the flagship service; blocks §14 | S    | yes                        |
| 2   | **Port T7 draft-guard to attack/zt mints**                                                              | attack mints ~600 rows per spurious version                    | S    | yes                        |
| 3   | **Enforce or retract auth compensating controls** (forced re-auth, refresh rotation, dead flags, docs)  | Documented MFA offsets don't exist                             | M    | yes                        |
| 4   | **Docs truth pass** (architecture.md, README, D-015 dedupe, D-006 supersession, OpenAPI reviewer purge) | architecture.md actively misleads new devs/agents              | M    | yes                        |
| 5   | **Deliverable release-to-client + client home hero**                                                    | Closes the spec's core client promise                          | L    | partly                     |
| 6   | **Backup/restore runbook + scripted snapshots + restore test**                                          | Empty runbooks; FedRAMP target with no DR story                | M    | mostly (drill needs-David) |
| 7   | **infra/terraform skeleton + deploy runbook**                                                           | Sprint-3-planned; blocked on David's cloud decisions           | L    | no (human-gated)           |
| 8   | **Rate limiting on auth + run-AI** (Redis idle and composed)                                            | Unthrottled login/register; run-AI is the expensive path       | M    | yes                        |
| 9   | **§15.5 filenames for CSF Playbook + Risk Register exports**                                            | Spec: every download link; two biggest exports don't comply    | S    | yes                        |
| 10  | **Framework-majors bundle** (Next 15/16, React 19, Tailwind 4, Node 22; D-018)                          | Next 14 EOL runway; 5 highs are 15.x-only                      | L    | yes, e2e-netted            |

Honorable mentions: redaction preview/approve gate, `/admin/audit` viewer, `llm_calls.client_id`, CSF POA&M fields, DoD 152-activity completion, i18n implement-or-rescind, ATT&CK grid pagination, commit the v2 Work Order to `reference-docs/`.

**Disposition (David, 2026-07-08):** Sprint 3 = items 1, 2, 3, 8, 9 + `llm_calls.client_id` + docs truth pass (item 4) + loop-gate hygiene → `SPRINT_3.md`. Item 10 → Sprint 4. Items 5 + suggestions → Sprint 5 candidates. Items 6/7 → needs-David track.
