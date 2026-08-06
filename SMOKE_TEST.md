# SHIELD v2 — Pre-Prod Smoke Test

A human runtime pass over the core flows. The deterministic logic is unit-tested;
this covers what needs eyes on a running app (UI, navigation, generated
documents, live AI). Work top-to-bottom in one sitting.

> **Automation note (sprint-1 smoke sweep):** items annotated `(sN-*.spec.ts)`
> are now covered by a green Playwright smoke spec under `e2e/smoke/`. Run the
> whole suite with `cd e2e && npx playwright test`. Items left unchecked still
> need a human: section 10 (eyeball generated documents), section 14 (one
> live-AI run with a real key), plus a few UI-visibility nuances noted inline.

## 0. Bring-up

- [ ] Copy `.env.example` → `.env`; set `NEXTAUTH_SECRET` (a long random string).
- [ ] `docker-compose up --build`; wait for `db`, `minio`, `keycloak`, `api`, `web` to report healthy.
- [ ] API docs load: `http://localhost:8000/docs`.
- [x] Web loads: `http://localhost:3000` (marketing home renders, no console errors). (s0-home.spec.ts)
- [ ] No `worker` service starts — AI is synchronous (confirm none is referenced).

## 1. Onboarding & auth (A1, A3, B1)

- [ ] Register the **first** user → becomes **admin** (bootstrap).
- [ ] As admin, create a client (e.g. "Acme") and approve a domain (e.g. `acme.test`).
- [x] Register a user with a brand-new, never-approved email domain → **self-registration succeeds** and the tenant is **auto-provisioned** (D-034, open self-registration); the user lands signed in on `/intake`. (s1-signup-errors.spec.ts — "a brand-new user self-registers and lands signed in on /intake"; backend `test_auth_routes.py::test_register_new_company_domain_provisions_client` / `test_register_generic_provider_gets_own_client`)
- [x] Register a user `@acme.test` → joins as a **client** role. (s3-selfassessment.spec.ts registers `qa+<stamp>@atlas.example`; s13-isolation.spec.ts proves a fresh approved-domain registrant gets the **client** role — `/admin/*` renders "Not authorized" for them)
- [ ] Sign out / sign in works; session persists on refresh.
- [x] Client user sees **no** "Deliverables"/admin links anywhere (A1). (s3-selfassessment.spec.ts — zero admin/deliverables links on the client shell `/assessments`; s13-isolation.spec.ts — admin URLs blocked. "Anywhere" is not an exhaustive crawl of every page.)
- [x] No "reviewer" role exists anywhere in the UI (A3). (s0-home.spec.ts asserts the home copy; T1 additionally verified a repo-wide grep — zero "reviewer" matches anywhere in `apps/web/src`)

## 2. Admin management (B2)

- [x] `/admin/management`: create another client + add/remove a domain; list reflects changes. (s2-management.spec.ts drives the `/admin/management` UI ITSELF, not the admin API: creates a timestamped client via the form, approves a `.example` domain, asserts both reflected in the rendered list, removes the domain, asserts the removal reflected.)
- [x] Client switcher works; the active client scopes what admin sees. (s13-isolation.spec.ts — the active-client switch is driven via the `/api/active-client` cookie API, not the UI widget; the scoping itself — X-Client-Id data plane — is fully asserted)

## 3. Intake & client self-assessment (C6, C8, A2, A4)

- [x] As a client, run intake; UI says "**assessment**" everywhere (not "engagement") (A2). (s3-selfassessment.spec.ts)
- [x] Open a CSF self-assessment; fill a few, **Save-and-exit**, return → answers persist. (s3-selfassessment.spec.ts persist test — reopens the exact created draft)
- [x] CSF questions are the **verbatim** interview prompts (C8). (s3-selfassessment.spec.ts — "CSF questionnaire renders the verbatim subcategory outcome prompts" asserts the rendered GV.OC-01/02/03 outcome text matches the catalog VERBATIM. Source of record: apps/api/app/csf/catalog.py SUBCATEGORIES — the deterministic CSF catalog the questionnaire renders from, transcribing the canonical NIST CSF 2.0 Final outcome statements; SHIELDv2_Master_Spec.txt §7 defines the subcategory model, not the per-item text.)
- [x] **DoD ZT shows only 3 levels** (A4). (s3-selfassessment.spec.ts — DoD ZtStagePicker asserts exactly 3 radios. NOTE: only the DoD client questionnaire is run; a CISA *client self-assessment* pass is not exercised — CISA is covered admin-side in s6-zt.spec.ts.)
- [x] Submit a self-assessment → status moves to submitted / under review. (s3-selfassessment.spec.ts submit test)

## 4. Tech Debt service (D1)

- [x] Admin opens / extracts a Tech Debt capability list. (s4-techdebt.spec.ts)
- [x] **Dashboard row** shows: capabilities count, annual cost, categories, to-consolidate/cut, low-confidence rows. (s4-techdebt.spec.ts — asserts the KPI cards render with their labels; the numeric values are not cross-checked against the uploaded data)
- [x] Edit a capability cell → its AI-confidence badge clears (human-curated). (s4-techdebt.spec.ts)
- [x] After **release**, the CLIENT opens the software-portfolio dashboard from `/documents` ("View dashboard") → KPI cards, spend-by-category bar, tool-sprawl donut, functional-redundancy cards, and a searchable inventory table render (D-035). (s29-tech-debt-dashboard.spec.ts)

## 5. ATT&CK service (D2, C2)

- [x] Start an assessment; matrix + **heatmap** render. (s5-attack.spec.ts)
- [x] Click **Run AI (mitre_map)** → "Updated N fields across M techniques"; matrix/heatmap refresh. (s5-attack.spec.ts)
- [x] Open a technique panel → **D/P/R tool chips + rationale** show; **Lock** checkbox toggles. (s5-attack.spec.ts)
- [x] Lock a technique, Run AI again → locked row **unchanged** + absent from "what changed" (C2). (s5-attack.spec.ts)
- [ ] Approve → workspace goes read-only.
- [x] After **release**, the CLIENT opens the interactive ATT&CK coverage dashboard from `/documents` ("View dashboard") → KPI cards, coverage-by-tactic bar + coverage-mix donut, Detect/Prevent/Respond rings, blind-spot cards, and a searchable per-technique matrix render (D-035). (s27-attack-dashboard.spec.ts)

## 6. Zero Trust service (D3)

- [x] Questionnaire renders by pillar; set a capability's **current** and **Target**. (s6-zt.spec.ts)
- [x] **Run AI (zt_score)** → current/target suggestions applied (DoD clamps to ≤3). (s6-zt.spec.ts)
- [x] Gap list reflects per-capability targets; **12-month roadmap** card groups gaps by month. (s6-zt.spec.ts — spot-checks: gap list renders against the target stage + roadmap shows "Month N" groups; not every capability/month is cross-checked)
- [x] After **release**, the CLIENT opens the Zero Trust maturity dashboard from `/documents` ("View dashboard") → KPI cards, current-vs-target maturity radar, and per-pillar deep-dive cards render (D-035). (s28-zt-dashboard.spec.ts)

## 7. CSF full Playbook (D4)

- [ ] Admin reviews the client's CSF self-assessment.
- [x] In the **Playbook panel**: **Seed Working Profiles** → ~106 subcats × tiers. (s7-csf-playbook.spec.ts — enterprise roll-up = 106 rows)
- [x] **Run AI (csf_score)** → dimensions + narrative drafted. (s7-csf-playbook.spec.ts)
- [x] **Dimension editor**: pick tier + subcategory, set the five 0/1/2 scores, toggle **Evidence on file** → confirm **total/level/cap** update live (no-evidence caps level ≤ 2). (s7-csf-playbook.spec.ts — evidence-cap math asserted)
- [x] **Enterprise roll-up** table: each subcategory shows tier levels, enterprise level, **rule #**, target, gap, **P1/P2/P3**. (s7-csf-playbook.spec.ts — 106-row table asserted; the full column contract (rule #, gap_priority P2) is verified end-to-end for one representative row, not per-subcategory)
- [x] **Export** → 5 files appear (XLSX, exec PDF/Word, full PDF/Word) with download links. (s7-csf-playbook.spec.ts — all 5 downloaded to `e2e/artifacts/`)

## 8. Risk Register (E)

- [x] `/admin/risk-register` for a client with **only** ATT&CK → **locked** state lists what's missing. (s8-risk-register.spec.ts)
- [x] Add a CSF or ZT assessment → gate **unlocks**. (s8-risk-register.spec.ts — adds ZT service, unlocks on reload)
- [x] **Generate** → entries appear; **tier is code-derived** (e.g. High × Catastrophic = Critical); KPI cards + **5×5 heatmap** render; cited links are only ones from the client's assessments. (s8-risk-register.spec.ts — engine tier mirror asserted per entry)
- [x] **Regenerate** → version increments. (s8-risk-register.spec.ts — delta-asserts version bump)
- [x] **Export** → XLSX/PDF/Word download. (s8-risk-register.spec.ts — all 3 downloaded to `e2e/artifacts/`)
- [x] After the register is **finalized** (exported), the CLIENT opens the Risk Register dashboard via the link on `/documents` → KPI cards, the **5×5 likelihood×impact matrix**, tier-mix donut, per-axis bars, and the full register table render (D-035). (s30-risk-dashboard.spec.ts)

## 9. Messaging (C7)

- [x] On a service workspace (admin) and the client's self-assessment page, the **message thread** shows. (s9-messaging.spec.ts)
- [x] Client posts a message → appears for admin; admin replies → appears for client. (s9-messaging.spec.ts — two-context round-trip)
- [x] `/admin/messages` **inbox** lists threads with **"N new"** unread badges; opening a thread clears its unread. (s9-messaging.spec.ts)

## 10. Exports & documents — eyeball each file

Deliverable _content_ is now locked by `pytest -m unit` export-content tests
(cited per box); reportlab PDFs are read back with `pypdf.PdfReader`, Word with
`docx.Document`, and workbooks with `openpyxl`. Only the visual appearance,
which no test can assert, stays a human check (the last box).

> **Ready for review:** s7/s8 save 8 generated artifacts to `e2e/artifacts/`
> (gitignored). As of Sprint 3 T4 every download name follows Master Spec §15.5
> — `{Company}_{Service}{MMDDYY}(_v{n})?(_{variant})?.{ext}` — so the files now
> land as e.g. `Atlas_Defense_Solutions_CSF_Playbook070926_v18.xlsx`,
> `…_v18_Executive.pdf/.docx`, `…_v18_Full.pdf/.docx`, and
> `Atlas_Defense_Solutions_Risk_Register070926_v20.xlsx/.pdf/.docx` (date +
> version vary per run; v1 carries no `_v{n}` suffix). Each was asserted HTTP 200
> with the correct content-type; **eyeballed by David 2026-07-09** against the
> `Atlas_Defense_Solutions_*` v19 (CSF) / v22 (Risk Register) artifact set.

- [x] **CSF executive briefing** PDF content: client name, document title, a CSF function name, a known gap row. (test_playbook_export_content.py, `test_exec_pdf_carries_client_title_function_and_gap`)
- [x] **CSF full playbook** PDF content: client, title, methodology, per-function detail, appendix rows. (test_playbook_export_content.py, `test_full_pdf_carries_client_title_function_and_gap`)
- [x] Both **CSF .docx** files: title, headings, scorecard table headers, a known maturity cell value. (test_playbook_export_content.py, `test_exec_docx_heading_scorecard_and_maturity_cell`, `test_full_docx_heading_scorecard_and_maturity_cell`)
- [x] **CSF .xlsx**: Enterprise + per-tier sheets + About cover, plus the Action Plan sheet headers and priority default-vs-override (§19). (test_csf_playbook_export.py + test_playbook_export_content.py)
- [x] **Risk Register** PDF / Word carry the title, client, and a known entry; XLSX 5x5 matrix + entries + blank governance columns. (test_risk_register.py, `test_pdf_carries_title_client_and_a_known_entry`, `test_docx_carries_title_client_and_a_known_entry`, `test_export_renders_and_stores_three_files`)
- [ ] **Visual appearance only** (human, optional): maturity/level cell shading, heatmap colors, spacing, and page-breaks. The tests assert values, not layout or color.

## 11. Auto-versioned docs (C3)

- [x] After a Run-AI on any service, the workspace shows the **"regenerate to refresh"** nudge. (s11-staleness.spec.ts)
- [x] Finalize / export → nudge clears on reload. (s11-staleness.spec.ts — approve + finalize clears the nudge)

## 12. Navigation / a11y / no-dead-ends (C6, F)

- [ ] Every admin + client page has top-nav; **no 404s** clicking around.
- [x] **Tab** from page load → first focusable is **"Skip to content"**; activating it jumps to `#main-content`, and the landmark shows a **visible** focus ring (test on admin + on `/account`, `/messages`, `/assessments`). (s12-a11y-nav.spec.ts — asserts hash becomes `#main-content`, focus lands ON the landmark, AND the landmark renders a non-zero outline width; the final-audit pass added `tabindex="-1"` to every `<main id=main-content>` per WAI-ARIA skip-link practice, and the seven-issue pass removed the `outline-hidden` class that was cancelling the ring — see §33)
- [x] Keyboard-navigate a workspace (radios, selects, buttons all reachable/operable). (s12-a11y-nav.spec.ts — CSF radio Space-to-answer + submit button enabled, plus arrow-key roving-tabindex on the TierPicker radiogroup (ArrowRight moves focus + follows `tabindex`, wraps at the ends) added in S2 T6; `select` controls are not keyboard-driven by the spec)
- [x] Each terminal state has an onward link (no dead ends). (s12-notfound.spec.ts — 404 recovery links asserted; the admin not-authorized state renders onward links via `admin/layout.tsx` with its copy asserted in s13; other terminal states are not enumerated)
- [x] Every `/home` service card is clickable and lands on a real destination for its own phase (report-ready → dashboard or `/documents`, in-progress → the self-assessment, otherwise `/assessments`). (s31-home-service-links.spec.ts — the cards were previously bare, unlinked `Card`s: a client could see a service and had no way to open it. See §33.)
- [x] `/admin/active` is gone from the nav and redirects to `/admin/queue` — no stub page with a single "go elsewhere" button. (s35-active-redirect.spec.ts. See §33.)

> **a11y roving-tabindex — FIXED in S2 T6** (`137727b`; asserted green by
> s12-a11y-nav.spec.ts): `TierPicker` / `ZtStagePicker` now implement WAI-ARIA
> radiogroup roving-tabindex — the selected radio (or the first, if none) is the
> sole `tabIndex=0` and Arrow Right/Down / Left/Up move focus with wrap. Focus
> movement does NOT auto-select (select stays on Space/Enter/click) so the
> auto-save PATCH is not flooded — see the inline comment in the components. The
> risk heatmap likelihood labels also gained `scope="row"` so Chromium exposes
> them as `rowheader` (s8 asserts `getByRole('rowheader')`). (The earlier
> skip-link landmark-focus gap was FIXED in the final-audit pass: `tabindex=-1`
> on every `main#main-content`.)

## 13. Access control & tenant isolation (F)

- [x] As a **client** user, hitting an admin URL (e.g. `/admin/risk-register`) is blocked. (s13-isolation.spec.ts — renders "Not authorized", not data)
- [x] As admin, switch to client **B**: client **A**'s data is unreachable on the B-scoped data plane → **404**, not data. (s13-isolation.spec.ts — X-Client-Id data plane: Beacon active → Atlas latest 404. NOTE the original "open A's service URL → 404" wording does not match the shipped app: navigating an admin *workspace URL* deliberately auto-switches the active client to the service's owner (`EnsureActiveClient`, an admin convenience — Kentro consultants serve all tenants) and then shows data. The security boundary is the server-side X-Client-Id scoping, which IS asserted.)
- [x] Client never sees another client's data anywhere. (s13-isolation.spec.ts — client is server-side scoped to its own client_id; cross-tenant GETs return 404 / empty)

## 14. Live AI (optional but recommended)

> **Provider-agnostic (Sprint 4 T6):** the live path is now selectable across
> `anthropic` / `openai` / `gemini` via `SHIELD_LLM_PROVIDER` (D-024). The egress
> contract is identical for all three — redaction and the `llm_calls` audit row
> run above the provider seam — so this check proves the *selected* provider,
> whichever it is.
>
> **Now codified (Sprint 6 T1 / D-026), still key-gated.** The 2026-07-12 manual
> smoke first proved the Anthropic path (`claude-sonnet-5`: real suggestions,
> redaction stripped `{client_org: 2, name: 2, email: 2}`, a correct `llm_calls`
> row, no PII). That smoke is now a **committed opt-in spec**
> (`apps/api/tests/live/test_live_ai.py`, marked `@pytest.mark.live`) plus a
> one-command script (`apps/api/scripts/smoke_live_ai.py`). Both **self-skip
> without a key**, so the boxes below stay **unchecked on purpose** — CI runs
> `pytest -m unit tests/unit` and never collects the live spec, and no committed
> spec runs a real call in a keyless pipeline. Check a box only after running the
> opt-in path with a real key on your machine (procedure below).
>
> **✅ GCP-validated 2026-07-15 — `vertex` / `gemini-2.5-flash` (D-029).** Dave's
> box, ADC-only (no static key): the Vertex provider path was exercised live
> through the redaction seam. The one-command smoke passed (real `csf_score`:
> 364 in / 307 out tokens, `redacted_counts == {email:2, name:2, client_org:2}`,
> `llm_calls` row `provider=vertex`/`mode=live`/`status=completed`, no PII). Boxes
> proven by that opt-in run are checked below; they remain **CI-skipped keyless**
> (the live spec is never collected by `pytest -m unit tests/unit`). Two adapter
> defects were found and fixed during this sweep (see §14.1).

- [ ] Set `SHIELD_LLM_MODE=live`, `SHIELD_LLM_PROVIDER=<anthropic|openai|gemini|vertex>`, that provider's key (`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY`; `vertex` uses ADC, no key) and a matching **current** `SHIELD_LLM_MODEL` (e.g. `claude-sonnet-5` / `gpt-4o-mini` / `gemini-1.5-pro` / `gemini-2.5-flash` — **not** `claude-opus-4-7`, a now-rejected placeholder, see D-026) in `.env`; restart `api`. Boot itself is now a check: live + missing key / unimportable SDK / placeholder model / (vertex) unresolvable ADC **refuses to start** (T0/D-029 preflight). *(vertex/gemini-2.5-flash boot verified 2026-07-15.)*
- [x] Run the one-command smoke: `docker compose exec -T api python -m scripts.smoke_live_ai` (with a live `.env`) → prints the real response + the `llm_calls` row and asserts mode=live / status=completed / tokens set / `redacted_counts` populated / no PII. (Equivalently: `… api pytest -m live tests/live -q`.) *(GCP-validated 2026-07-15, vertex/gemini-2.5-flash — passed.)*
- [ ] Run **one** Run-AI through the UI (e.g. csf_score) → real suggestions return; `llm_calls` has a logged, **redacted** entry with the correct **`provider`**/**`model`** and a **`client_id`** set (Sprint 3 T5 tenant attribution); no PII in the log.
- [ ] Selecting a provider with its key unset, or a not-implemented provider (`azure_openai`/`bedrock`/`local`), fails loudly at startup — no silent fallback.

### 14.1 Live-AI parity sweep — all five purposes (Sprint 6 T7, opt-in)

> **Extended from CSF-only to every AI purpose, still key-gated.** T1 codified
> the `csf_score` path; T7 extends the SAME opt-in spec
> (`apps/api/tests/live/test_live_ai.py`) to a parametrized sweep over all five
> purposes — `csf_score`, `zt_score`, `mitre_map`, `risk_synthesize`,
> `tech_debt_extract`. Every case plants the identical canonical PII (org/name/
> email, twice each) so `redacted_counts` must equal `{email: 2, name: 2,
> client_org: 2}` for every purpose, asserts a complete live `llm_calls` row and
> no PII in the response, **and** asserts the response parses into the container
> the route layer reads (`scores` / `capabilities` / `techniques` / `entries` /
> `ExtractedCapability` rows) — the per-adapter parse check. Like §14 it is
> `@pytest.mark.live` only, lives outside `tests/unit`, and **self-skips without
> a key**, so CI (`pytest -m unit tests/unit`) never collects it and the boxes
> below stay **unchecked on purpose** until run with a real key.
>
> **✅ GCP-validated 2026-07-15 — `vertex` / `gemini-2.5-flash` (D-029).** All
> five `test_live_purpose_contract[*]` cases passed live against Vertex (opt-in,
> CI-skipped keyless). The sweep surfaced and fixed **two real adapter defects**
> in the shared generateContent path that no keyless unit test had exercised:
> **(1)** `google-auth` needs its `[requests]` extra for the token-refresh
> transport — the first live token refresh raised `ImportError` without it;
> **(2)** gemini-2.5 "thinking" spent an unbounded, run-variable slice of the
> output budget and truncated the longer `csf`/`risk`/`zt` drafts mid-JSON, which
> `_parse_generate_content` silently returned as "completed" and only died later
> as an opaque `JSONDecodeError`. Fix: a **loud `finishReason` guard** (a non-STOP
> reason now raises at the parse seam, failing the `llm_call` cleanly), the shared
> output cap raised 4096→8192, and a **bounded `thinkingConfig.thinkingBudget`**
> (2048) added for 2.5+ models only (gemini-1.5 API-key path untouched). All three
> are `pytest -m unit` locked in `test_llm_providers.py`.

- [x] Run the full sweep: `docker compose exec -T api pytest -m live tests/live -q` (with a live `.env`) → all five `test_live_purpose_contract[*]` cases pass (each: mode=live / status=completed / tokens set / `redacted_counts == {email:2, name:2, client_org:2}` / no PII / response parses to the documented shape). *(GCP-validated 2026-07-15, vertex/gemini-2.5-flash — 5 passed.)*
- [x] `csf_score` — real suggestions parse to a `{"scores": [...]}` object.
- [x] `zt_score` — real suggestions parse to a `{"capabilities": [...]}` object.
- [x] `mitre_map` — real suggestions parse to a `{"techniques": [...]}` object.
- [x] `risk_synthesize` — real suggestions parse to an `{"entries": [...]}` object.
- [x] `tech_debt_extract` — real response parses into `ExtractedCapability` rows.

## 15. Security headers

- [x] `curl -I http://localhost:3000`: confirm **CSP**, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Strict-Transport-Security`, `Permissions-Policy`. (s15-headers.spec.ts — all six present, set in `apps/web/next.config.mjs`)
- [x] App still functions under CSP (no blocked resources in the console). (s15-headers.spec.ts — signed-in admin dashboard shows zero CSP-blocked resources)

## 16. Deliverable release flow (Sprint 5, §12 / §6.7 — T1)

The §12 release rule: a client sees a deliverable ONLY after a consultant
explicitly releases the finalized deliverable. Backend contract (release route,
client list, artifact access) is `pytest -m unit` covered; the runtime effects
below are e2e-proven.

- [x] Admin finalizes a deliverable, then **releases** it; a real client of that tenant sees the released row. (s17-documents.spec.ts — API finalize+release v1, client sees the row)
- [x] A **finalized-but-unreleased** deliverable never appears for the client. (s17-documents.spec.ts — v2 finalized, left unreleased, absent from the client page)
- [x] A client can **download** an artifact of a released own-tenant deliverable (200 + §15.5 filename). (s17-documents.spec.ts — client PDF download 200, content-disposition carries the §15.5 name)
- [ ] Release requires `finalized_at` (typed 409 `not_finalized`); re-release is an idempotent 200 no-op; audit row `*.deliverable.released` written; artifact deny paths (unreleased / cross-tenant / non-deliverable). (`pytest -m unit` contract tests, not an e2e checkbox — no runtime UI eyeball surface)

## 17. Client `/documents` — WHAT YOU'VE RECEIVED (Sprint 5, §6.7 — T2)

- [x] Client nav gains a **Documents** entry; the page lists released deliverables (service label, title, **Final** badge). (s17-documents.spec.ts)
- [x] Per-format **download link** streams 200 with a §15.5 filename. (s17-documents.spec.ts — PDF download 200, `application/pdf`, §15.5 content-disposition)
- [x] Empty state renders per the no-dead-ends rule when a client has no released deliverables (§12). (s17-documents.spec.ts, Sprint 8 T6: asserted in a fresh per-run throwaway tenant that never releases a deliverable, so the "No documents yet" state is proven by construction; the persistent s17 tenant always carries a released row, so this uses its own tenant.)

## 18. Client `/home` dashboard + value-loop card (Sprint 5, §6.4 / §2.5 — T3/T4)

- [x] Client with **no** released report sees next-step guidance (Welcome heading + "Start an assessment"), **not** the "report is ready" hero. (s18-home.spec.ts — hero-absent guidance state)
- [x] After a release, the same client's `/home` shows the **hero** ("report is ready" + View reports / Download PDF). (s18-home.spec.ts — hero-present state)
- [x] A signed-in **client** hitting `/` lands on `/home`; a signed-in **admin** lands on `/admin`. (s18-home.spec.ts — both role landings)
- [x] `/home` leaks **no scoring math** (§6.4) — no percentage renders. (s18-home.spec.ts — `/\d+%/` count 0)
- [x] **Value-loop card** (§2.5) is absent before any release and, after a scored+released CSF, renders a **NIST CSF 2.0** gap count with **Pending** for services lacking released data (never a fake 0). (s19-value-loop.spec.ts)
- [x] The value card leaks no scoring math — no percentage renders. (s19-value-loop.spec.ts — `/\d+%/` count 0)

## 19. CSF POA&M / action plan (Sprint 5, step 10 — T5)

- [x] The gap-analysis view renders an **action-plan editor** card per enterprise gap; Characterize (accept/mitigate/transfer/avoid) + owner **auto-save** and survive a `page.reload()`. (s7-csf-playbook.spec.ts — `gap-action-{code}` card, `selectOption("mitigate")` + owner blur each waits on the gap-actions PUT, values survive reload)
- [x] The playbook **XLSX** gains an **Action Plan** sheet (characterization / owner / deadline / resources / success criteria / poam_ref; priority defaults from `gap_priority()`, override wins). (test_playbook_export_content.py, `test_xlsx_action_plan_sheet_has_expected_headers`, `test_xlsx_action_plan_only_lists_gaps`, `test_xlsx_action_plan_priority_defaults_from_gap_priority`, `test_xlsx_action_plan_priority_override_wins`)

## 20. Redaction preview gate (Sprint 5 — T6)

- [x] From a Run-AI surface, the **offered** "preview what will be sent" affordance shows the **redacted payload** + **removed counts** WITHOUT egress, then Run-AI still works. (s7-csf-playbook.spec.ts — `ai-preview-button` → POST `/ai/preview`, payload has `subcategories`, `ai-preview-removed-total` visible, then the real Run-AI runs)
- [ ] Preview creates **no** `llm_calls` row and constructs no provider; admin-only; the AI rate limiter applies; preview output equals `redact_payload()` of the run-ai builder's payload for the same state. (`pytest -m unit` contract tests — no runtime eyeball surface for the "no row created" invariant)

## 21. `/admin/audit` viewer (Sprint 5 — T7)

- [x] Admin nav gains **Audit**; the page renders the **Audit log** two-tab viewer (Activity / AI calls). (s20-audit.spec.ts)
- [x] An audited action performed in-test (`csf.run_ai`) appears in the **Activity** tab (filter by action prefix). (s20-audit.spec.ts)
- [x] The **AI calls** tab lists the fixture-mode `llm_calls` row (purpose `csf_score`, `fixture`). (s20-audit.spec.ts)
- [x] **Correlation-id click-through** links the two tabs (clicking an AI call's correlation jumps to Activity filtered by that id). (s20-audit.spec.ts)
- [x] The viewer is **read-only** — no mutation affordances on the append-only store. (s20-audit.spec.ts — only filter/apply/clear controls; construction-level per T7)
- [ ] Every filter (target_type, actor, date range / client_id, provider, status) and cursor pagination; client-role 403. (`pytest -m unit` filter/pagination contract tests)

## 22. Live-AI enablement — runnable path + boot preflight (Sprint 6, T0 / D-026)

The live path stopped 500ing on first use: `anthropic` is a declared runtime dep,
the stale `claude-opus-4-7` default is gone, and a misconfigured live deploy now
**fails LOUDLY at boot** instead of mid-engagement. The live call itself stays
key-gated (§14/§14.1); the boot-preflight logic is `pytest -m unit` proven.

- [x] Live + missing provider key / unimportable SDK / placeholder model **refuses to boot** (loud `RuntimeError`); fixture mode is unaffected. (test_config.py — `test_live_mode_missing_anthropic_key_raises_at_boot`, `test_live_mode_missing_sdk_raises_at_boot`, `test_live_mode_placeholder_model_raises_at_boot`, `test_live_mode_openai_missing_key_raises_at_boot`, `test_live_mode_unimplemented_provider_raises_at_boot`, `test_fixture_mode_unaffected_by_llm_preflight`)
- [x] A valid live config boots cleanly; the default model is **not** the stale `claude-opus-4-7` placeholder. (test_config.py — `test_live_mode_valid_anthropic_boots`, `test_default_model_is_not_the_stale_placeholder`)
- [ ] A real end-to-end live Run-AI with a provider key. (key-gated — see §14; no committed spec runs a live call in a keyless pipeline)

## 23. Full dependency-health readiness + operator view (Sprint 6, T3)

`/ready` moved from a DB-only `SELECT 1` to a per-dependency matrix (db, redis,
minio, keycloak-dormant, LLM readiness); `/health` liveness stays cheap. The
`/admin/health` operator page renders the matrix.

- [x] `/ready` reports a per-dependency matrix; `/health` liveness touches no dependency. (test_readiness.py — `test_ready_reports_full_dependency_matrix`, `test_health_liveness_does_not_touch_dependencies`)
- [x] Any down **required** dependency flips `ready=false` and **names the offender**; keycloak is marked dormant/not-required and the fixture-mode LLM check is informational-only. (test_readiness.py — `test_ready_flips_false_and_names_offender_when_redis_down`, `test_ready_flips_false_when_minio_down`, `test_ready_marks_keycloak_dormant_and_not_required`, `test_ready_llm_fixture_mode_ok_and_informational`, `test_ready_stays_true_when_only_informational_check_off`)
- [x] `/ready` redacts per-dependency `detail` for **anonymous** callers (LB/k8s still get statuses + offender names) and returns full operator detail to **authenticated** callers. (test_readiness.py — `test_ready_redacts_detail_for_anonymous_callers`, `test_ready_full_detail_for_authenticated_caller`; T10 hardening)
- [x] The `/admin/health` operator view renders every dependency row, an all-green overall badge, and a **degraded** badge naming the offender when a required dep is down. (HealthMatrix.test.tsx — vitest, in the `pnpm -F web test` gate)
- [x] Eyeball `/admin/health` in a browser against the running stack (all-green when healthy). (s25-admin-health.spec.ts, Sprint 8 T6: admin signs in, drives `/admin/health` against the live dev stack, and asserts the all-green overall status badge plus every dependency row.)

## 24. Real TOTP MFA (Sprint 6, T4 / D-027)

Real RFC 6238 TOTP on the custom-JWT stack: enroll → confirm (recovery codes
shown once) → login challenge. The D-020 boot-refusal on
`SHIELD_AUTH_REQUIRE_MFA` is gone; the flag now GATES enforcement. Backend flow
is `pytest -m unit` proven; the web enrollment/sign-in UI is now e2e-driven
(`s24-mfa.spec.ts`, Sprint 8 T4/T5).

- [x] Enroll → verify → login-with-TOTP happy path returns the real access/refresh pair. (test_mfa_routes.py — `test_full_enroll_then_login_with_totp`)
- [x] Wrong/expired TOTP rejected; verify-before-enroll and enroll-without-auth rejected; a pending token authorizes nothing but `verify-login` (an access token is refused as pending). (test_mfa_routes.py — `test_verify_rejects_wrong_code`, `test_verify_login_rejects_wrong_code`, `test_verify_before_enroll_is_rejected`, `test_enroll_requires_authentication`, `test_verify_login_rejects_access_token_as_pending`; test_totp.py — `test_verify_totp_accepts_current_and_rejects_wrong`, `test_verify_totp_tolerates_one_step_skew_but_not_two`)
- [x] Recovery-code login works and is **single-use**. (test_mfa_routes.py — `test_recovery_code_login_is_single_use`)
- [x] A non-enrolled user gets a normal session with no challenge (back-compat). (test_mfa_routes.py — `test_login_without_mfa_returns_pair_no_challenge`)
- [x] Wrong second-factor guesses feed the **account-lockout** counter at both verify-login and enroll-confirm (T10 hardening). (test_mfa_routes.py — `test_verify_login_failures_feed_account_lockout`, `test_enroll_verify_failures_feed_account_lockout`)
- [x] TOTP matches the RFC 6238 test vectors; the at-rest secret encrypt/decrypt round-trips and a bad ciphertext raises loudly. (test_totp.py — `test_totp_matches_rfc6238_vector`, `test_secret_encrypt_roundtrip`, `test_decrypt_bad_ciphertext_raises_loudly`, `test_recovery_codes_generate_and_hash_verify`, `test_provisioning_uri_shape`)
- [x] Eyeball the web sign-in MFA step + the account-page enrollment section (QR/secret, recovery-code display) in a browser. (s24-mfa.spec.ts, Sprint 8 T4/T5: part A enrolls on `/account` with a generated TOTP and asserts the shown-once recovery codes, then signs in through the UI TOTP step; part B redeems a recovery code and proves it single-use. This spec surfaced the MFA sign-in browser bug fixed in `f10b803`.)

## 25. Email verification + password reset (Sprint 6, T5 / D-028)

Real email verification + self-service reset over SMTP/MailHog. Tokens are
hashed at rest, single-use, time-bounded; resend/forgot are enumeration-safe.
Delivery is off by default, so the MailHog end-to-end e2e is **opt-in**; the
token/flow logic is `pytest -m unit` proven with delivery stubbed.

- [x] Registration issues a verification token + sends the email; `/auth/verify-email` stamps `email_verified_at`; a bad/expired/already-used token is rejected. (test_email_verification.py — `test_register_issues_verification_token`, `test_verify_email_sets_verified`, `test_verify_email_rejects_bad_token`, `test_verify_email_rejects_expired_token`, `test_verify_email_token_is_single_use`)
- [x] `resend-verification` and `forgot-password` return a **uniform** enumeration-safe response whether or not the account exists. (test_email_verification.py — `test_resend_verification_is_uniform_and_reissues`, `test_forgot_password_is_enumeration_safe`)
- [x] `/auth/reset-password` changes the password, is **single-use**, and enforces the weak-password policy. (test_email_verification.py — `test_reset_password_changes_password`, `test_reset_password_token_single_use`, `test_reset_password_rejects_bad_token`, `test_reset_password_enforces_policy`)
- [x] With `SHIELD_AUTH_REQUIRE_EMAIL_VERIFY=on`, an unverified user is blocked at login (typed `email_not_verified`) then allowed once verified. (test_email_verification.py — `test_login_blocked_when_require_email_verify_and_unverified`)
- [x] **MailHog end-to-end** — register → read the message out of the MailHog API → extract the token → complete verify / reset. (s21-email-verify.spec.ts — 2 tests) **Now RUNS (not skips) in dev + CI as of Sprint 7 T3 (`d95f5c7`):** `SHIELD_EMAIL_DELIVERY_ENABLED` defaults to `true` in `docker-compose.yml` (SMTP → the `mailhog` service), so both tests execute the real token flow through the wire on every run; T3's full-suite pass confirmed both green. (`SHIELD_AUTH_REQUIRE_EMAIL_VERIFY` deliberately stays `false` — flipping it breaks every e2e sign-in.)
- [x] Browser-drive the verify-email / forgot-password / reset-password **pages**: register, confirm the address from the emailed token on `/verify-email`, then request a reset on `/forgot-password`, complete it on `/reset-password`, and sign in with the **new** password. (s23-auth-pages.spec.ts, 2 tests.) Opt-in like s21 (SKIPS with delivery off; RUNS in dev/CI where delivery is on since Sprint 7 T3); both tests green standalone and in the full suite (Sprint 8 T3).

## 26. Seed → storage parity + demo data realism (Sprint 6, T2 / T8)

The seed now writes artifact bytes through `get_storage()` (the SAME backend the
API reads — MinIO under compose) and releases its deliverables, so a clean seed
produces a coherent, downloadable Atlas story (before T2 seeded downloads 410'd).

- [x] The real seeded Atlas client (`client@atlas.example`) opens `/documents` and **downloads a seeded released deliverable → 200** with the §15.5 filename and non-zero bytes (410 before the T2 seed→storage fix). (s17-documents.spec.ts — "seeded Atlas client downloads a SEEDED released deliverable (T2 storage parity)")
- [x] The seeded Atlas **Risk Register** renders on `/admin/risk-register` with **code-derived tiers** (every entry's tier equals `tierFor(likelihood, impact)` — never hard-coded) and its XLSX/PDF/Word exports download 200 with §15.5 filenames. (s8-risk-register.spec.ts — "seeded Atlas Risk Register renders code-derived tiers and its exports download (T8 demo seed)")
- [x] `scripts/demo-reset.(sh|ps1) --demo`: `down -v` → `up -d --build` (production web image) → wait `/ready` full-matrix → seed → **fail-loud** web-wait (a stalled web build now exits non-zero and dumps `docker compose logs web`, closing the old silent-success gap). The post-reset journey is asserted by a committed spec: `/ready` all-green, `/sign-in` serves 200 with the strict CSP (prod-build proof), admin and client both sign in through the standalone build, the client `/home` shows the released-report hero, and a seeded `/documents` deliverable downloads with non-zero bytes. (`e2e/demo/demo-journey.spec.ts` — 4 tests; self-skips unless `SHIELD_DEMO_SMOKE=1`, run right after `demo-reset.sh --demo`. Sprint 9 T8, D-033. Plain no-flag invocation still targets the base compose.)

## 27. Hosted-demo compose + CI demo job (Sprint 6 T9; Sprint 9 T9)

`docker-compose.demo.yml` is a thin override running web as a **production**
Next standalone build (not `next dev`), fixture-by-default with live only when a
key is supplied. Cloud/terraform is explicitly NOT touched (needs-Dave). Sprint 9
T9 adds a CI `demo` job that runs the whole bring-up on every PR to `main`.

- [x] `docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --build` builds `shield-web:demo` and serves web (200 at `/` + `/sign-in` with CSP headers, prod build) + api (`/ready` full-matrix green) against the real services. (e2e/demo/demo-journey.spec.ts — the spec runs against exactly this prod-build stack after `demo-reset.sh --demo`, asserting `/ready` full-matrix green and `/sign-in` 200 with the strict CSP; first eyeballed end-to-end in Sprint 6 T9)
- [x] The CI `demo` job (`.github/workflows/ci.yml`) logs `docker compose version` and hard-fails below 2.24, runs `bash scripts/demo-reset.sh --demo` (builds `shield-web:demo`, seeds inside the script), then `SHIELD_DEMO_SMOKE=1 npx playwright test demo/` (e2e/demo/demo-journey.spec.ts) green, with always-run compose-ps/logs diagnostics + `if: always()` artifact upload. (demo job — first green PR run 2026-07-22 on PR #44: CI run 29939798138, "Demo (hosted-demo reset + journey spec)" pass in 2m48s, actions/runs/29939798138/job/88990483196)

## 28. Security hardening on the new auth surfaces (Sprint 6, T10)

The T10 pass hardened the T4/T5 surfaces and ran the audit set. The two fixed
findings are re-asserted by the specs above (§23 anonymous `/ready` redaction,
§24 MFA lockout integration).

- [x] MFA second-factor guesses feed the account-lockout counter; the counter resets ONLY on a fully successful login. (test_mfa_routes.py — see §24)
- [x] `/ready` reduces per-dependency `detail` to a generic string for anonymous callers. (test_readiness.py — see §23)
- [ ] Audit scans (bandit, `pnpm audit` root, `npm audit` e2e, pip-audit, gitleaks) clean or documented; no secret/key committed this sprint. (CI + manual — bandit exit 0, JS audit posture carried unchanged from Sprint 5 [0 high / 2 documented moderates], manual secret-diff scan clean; not a runtime checkbox)

## 29. Client release notification email (Sprint 7, T2 / D-030)

On deliverable release the shared `release_deliverable` helper (behind all four
services + the risk register) emails the tenant's active client-role users when
`SHIELD_EMAIL_DELIVERY_ENABLED` is on — best-effort, with the release as the
source of truth. The logic is `pytest -m unit` proven with the sender stubbed;
`s22-release-notify.spec.ts` (Sprint 8 T2) now also eyeballs the notification in
MailHog end-to-end for a real registered client of an isolated tenant.

- [x] Release with delivery on emails **exactly** the tenant's active client-role users; cross-tenant users and admins are never notified. (test_release_notification.py — `test_release_notifies_active_client_users_of_tenant_only`)
- [x] The notification body carries the **service**, deliverable **title/version**, and the `{WEB_BASE_URL}/documents` link. (test_release_notification.py — `test_notification_body_carries_service_title_version_and_documents_link`)
- [x] Delivery **off** → the release proceeds exactly as v3.3.0 with a loud skip log; **nothing** is sent. (test_release_notification.py — `test_delivery_off_sends_nothing_but_still_releases`)
- [x] An SMTP failure is logged **loudly** and the release is **not** rolled back (release is the source of truth). (test_release_notification.py — `test_smtp_failure_does_not_roll_back_release`)
- [x] **MailHog visible** — release a deliverable with delivery on and confirm the notification lands in MailHog (`:8025`) for the tenant's registered client, with the release subject + `/documents` link. (s22-release-notify.spec.ts — self-skips when delivery is off, mirroring s21)

---

## 31. Discard draft affordance (Sprint 9, T0 / T1 / T3 — D-031)

Every service now lets the consultant throw away an in-progress DRAFT instead of
approving a throwaway version to get it out of the way. The backend adds a
draft-only `POST .../discard` per service (`DISCARDED` status, D-031), the web
adds the app's first destructive-confirm dialog (the shared `DiscardDraftButton`
+ design-system Modal), and the three e2e preambles that used to
approve-away an open draft now discard it — a semantically honest reset that no
longer pollutes version history.

- [x] Each service exposes a **draft-only** `POST .../discard` that returns the record to `status='discarded'`, writes **exactly one** audit row (`capability_list.discarded` / `{csf,attack,zt}.assessment.discarded`), and is **idempotent** on re-discard (no second audit row). (test_discard_draft.py)
- [x] A **SUBMITTED** (CSF/ZT), **APPROVED**, or **RELEASED** record is not discardable → typed **409** `{reason:'not_discardable'}`; a **client** role → 403; an unknown / cross-tenant id → 404. (test_discard_draft.py)
- [x] After discard the **version trap** is closed: a discarded non-v1 draft leaves `_latest_` returning the prior approved/released version (or 404), and the next extract/create mints a **fresh** version with no `IntegrityError` (mint reads `max(version)`, unfiltered). (test_discard_draft.py — `test_techdebt_latest_404_when_only_draft_discarded` + the v3-after-discard cases)
- [x] Every **hidden latest-consumer** skips a discarded row — risk synthesis and the intake engagement cards read "latest non-discarded", and a child mutation / AI run into a discarded parent loses loudly (typed 409). (test_discard_draft.py)
- [x] The shared **`DiscardDraftButton`** renders **only** for a DRAFT, opens the design-system Modal stating what will be destroyed, and calls `onConfirm` **only** on an explicit confirm — cancel / ESC / backdrop are no-ops. (DiscardDraftButton.test.tsx)
- [x] **Browser proof** — with a draft open, clicking **Discard draft** → cancel is a no-op → confirming in the Modal throws the draft away and the tech-debt workspace re-enables a fresh extraction (a re-upload mints a brand-new draft). (s4-techdebt.spec.ts)
- [x] The three specs that used to **approve-away** an open draft now **discard** it instead, with post-preamble behaviour byte-identical (the `changed>0` / "AI 60%" / stale-nudge assertions are untouched). (s4-techdebt.spec.ts, s5-attack.spec.ts, s11-staleness.spec.ts)

---

## 32. Hybrid Keycloak OIDC sign-in (Sprint 9, T4–T7, D-032)

A real Keycloak (OIDC) sign-in now sits beside the credentials form, gated
behind `SHIELD_AUTH_OIDC_ENABLED` (default off). A Keycloak token is never
accepted as an API bearer. The browser round trip ends at `POST
/auth/oidc/exchange`, which verifies the token against the realm JWKS and mints
a native SHIELD pair only for an already-existing local account. There is no
JIT provisioning. `s26-oidc-login.spec.ts` drives both paths through the real
Keycloak login form and self-skips unless `E2E_OIDC=1`, so the default suite is
untouched.

- [x] Opt-in and dormant by default: with the flag off, `s26-oidc-login.spec.ts` reports **two skipped** tests and the `keycloak` provider is **absent** from `/api/auth/providers`, so the default suite count is unchanged. (s26-oidc-login.spec.ts)
- [x] Backend exchange contract: a Keycloak-shaped access token is accepted only when its RS256 signature, issuer, audience, and `azp` all check out **and** a matching active local account exists; every other case returns a typed dict-detail failure and **no** account is provisioned (no JIT). (test_oidc_exchange.py)
- [x] **Positive path** — `admin@kentro.example` (in Keycloak AND in the SHIELD DB) signs in through the real Keycloak form (`#username` / `#password`), lands authenticated, and the admin management list renders, proving the exchanged SHIELD bearer token authenticates a real API call end to end. (s26-oidc-login.spec.ts)
- [x] **Negative path** — `nolocal@atlas.example` (in Keycloak, NOT in the SHIELD DB) authenticates against Keycloak, the exchange refuses it (`oidc_no_local_account`), and `SessionExpiryGuard` signs the session out to `/sign-in?reason=oidc_exchange_failed` with the loud banner. (s26-oidc-login.spec.ts)
- [x] **Flag-off restoration** — after the flag is removed and `api`+`web` are recreated, `keycloak` reports `dormant` on `/ready`, the provider is gone, and the credentials suite signs in green. (s25-admin-health.spec.ts asserts keycloak dormant; s0/s2 credentials sign-in)

**Operator note (flip and restore).** The flag must never be committed on.

1. Add `SHIELD_AUTH_OIDC_ENABLED=true` to the repo-root `.env`.
2. `docker compose up -d --force-recreate api web` (web reads the flag at provider registration, api at boot readiness).
3. Only if `infra/keycloak/shield-realm.json` changed since it was last imported, wipe the keycloak volume so the new realm re-imports: `docker compose stop keycloak && docker volume rm shield-v2_keycloak-data && docker compose up -d keycloak`.
4. `E2E_OIDC=1 npx playwright test smoke/s26-oidc-login.spec.ts`.
5. Restore: remove the flag line, `docker compose up -d --force-recreate api web`, then re-run the default suite to confirm the credentials path still signs in.

## 33. Navigation dead ends removed (seven-issue pass, issues 1 / 5 / 6)

Three surfaces rendered but could not be acted on. See also §12.

- [x] **`/home` service cards are links.** Every card on the client home dashboard navigates, routed by that card's own phase — report-ready to the service dashboard (or `/documents` for a kind with no dashboard), in-progress to the self-assessment, everything else to `/assessments`. Clicking a "Report ready" card lands on a dashboard that actually renders, not the not-available fallback. (s31-home-service-links.spec.ts; unit: HomeDashboard.test.tsx "every service card must be a link". `dashboardPathFor()` in `lib/dashboards/routes.ts` is the single source of truth, shared with `/documents`.)
- [x] **`/admin/active` no longer dead-ends.** The nav entry points at `/admin/queue`; the old route redirects there so bookmarks still work, and "Active Work" is gone from the admin nav. (s35-active-redirect.spec.ts)
- [x] **The skip-to-content link produces a visible change.** The link always moved focus correctly; the ring was cancelled by `outline-hidden` on all 8 `<main id="main-content">` shells, so on a short page nothing appeared to happen. The class is removed and the rendered outline width is now asserted, not just the focus move. (s12-a11y-nav.spec.ts)

## 34. Client + user removal (seven-issue pass, issue 3 — D-036)

Removal is **soft** throughout, following the `archive_service` precedent:
archiving a tenant stamps `client.archived_at` (migration 0033) and retains every
assessment, deliverable and audit row.

- [x] Archive a client from the admin console → it disappears from the client list and the intake org index; its data is retained. (s33-admin-remove.spec.ts; test_admin_removal.py)
- [x] List a tenant's users and deactivate / reactivate one. (s33-admin-remove.spec.ts; test_admin_removal.py)
- [x] Deactivating yourself is refused with a typed D-016 error (locking yourself out of the only admin console is unrecoverable from the UI). (test_admin_removal.py)
- [x] A **deactivated user cannot sign in** — `/auth/login` now checks `is_active` (it did not before; refresh/MFA/reset did, so deactivation was a lie), the check sits after the password verify so the endpoint is not an account-existence oracle, and the sign-in form says "this account has been deactivated" rather than implying a bad password. (test_admin_removal.py; s33-admin-remove.spec.ts)
- [x] Deactivation kills an existing session — `active_refresh_jti` is cleared, so the user does not ride a valid refresh token to expiry. (test_admin_removal.py)

## 35. Intake queue is an index of organizations (seven-issue pass, issue 7)

- [x] `/admin/queue` lists **every** organization with pending intake, each row carrying its awaiting-review count — it previously opened onto whichever tenant was created most recently and rendered that as the page header. (s32-admin-org-index.spec.ts)
- [x] `/admin/queue/[clientId]` shows one org's intake detail above its own pending work, using the API's existing `client_id` filter. (s32-admin-org-index.spec.ts)

## 36. Runtime AI key + release control (seven-issue pass, issues 2 / 4 — D-037, D-038)

- [x] An admin can paste, replace and remove a provider API key on `/admin/management`; the key is **validated against the provider before it is stored**, so a typo is refused with the provider's own reason instead of silently taking AI offline. (test_admin_llm_key.py; s34-llm-key.spec.ts)
- [x] The stored key is encrypted at rest (Fernet, migration 0034), is never returned by any endpoint, never logged, and never lands in an audit `details` blob. (test_admin_llm_key.py asserts each)
- [x] A stored key takes effect on the next Run AI with **no restart**, and overrides `SHIELD_LLM_MODE=fixture`. (test_admin_llm_key.py)
- [x] The "AI is offline" banner renders on **every** admin page (it previously rendered on one of five workspaces) and links to the fix. (s34-llm-key.spec.ts)
- [x] While AI is offline, the first Run AI click warns that output will be canned and offers "Load a key" / "Continue offline"; removing the key re-warns on the very next Run AI in the same session. (RunAiGuard.test.tsx — 7 unit tests, including re-warn-after-removal and the two race cases below. `s34`'s browser assertion runs whenever the ATT&CK workspace is editable and self-skips when the seeded assessment is already released, so whether it exercises the dialog depends on DB state.)
- [x] A Run AI click made **before** the AI-status request resolves is held until the answer arrives — it never produces canned output unwarned. The first implementation failed open on an unresolved status, so under load the guard silently ran and wrote 1646 fields; found by the first full-suite run of `s34` (it had only ever been run standalone, where it skipped). (RunAiGuard.test.tsx "does NOT run when clicked before the status has loaded" + "honours a deferred click when the status turns out to be live"; `s34-llm-key.spec.ts` clicks eagerly on purpose to keep the regression pinned.)
- [x] A genuine AI-status **outage** still fails open — an unreachable status endpoint must not stop an admin working. That is a different case from "not asked yet", and the two are now distinct states. (RunAiGuard.test.tsx "fails open when the status endpoint is unavailable")
- [x] An admin can **release** a finalized deliverable from the workspace card, and the card reflects the released state afterwards. Before this, nothing in the product could release anything, so the client dashboards' release gate (D-035) was unsatisfiable and no client could ever see a dashboard. (s36-release-and-preview.spec.ts, self-seeding a finalized-but-unreleased service)
- [x] An admin can open a service dashboard **before** release (preview), reaching it on a cold URL with no active-client cookie; the payload is identical to what the client will see apart from a `released` flag. (s36-release-and-preview.spec.ts; backend test asserts preview == client view)
- [ ] Live path: paste a **real** provider key through the UI and confirm a Run AI produces live (non-fixture) output. Needs a human with a real key — the automated coverage stops at the validation contract with a substituted validator (§14 remains the live-AI section).


## 37. Tech Debt portfolio scope + security sign-off (D-039)

- [x] Extraction keeps **every** inventory row and classifies it, rather than dropping the non-security ones. A payroll system is extracted, not silently discarded — under the v1 prompt the guided review lost 9 of 21 rows and $742,440 of real spend with no disclosure. (test_tech_debt_security_classification.py; s37-security-signoff.spec.ts)
- [x] A capability the model calls **not security-related** stays in the ATT&CK tool subset until a consultant agrees. `valid_tools` is a hard allow-list on what the model may cite, so a tool dropped by mistake becomes uncitable and its technique reads as *uncovered* rather than unassessed. (test_tech_debt_security_scope.py; s37 asserts it through the API while the queue shows it)
- [x] Signing off on the negative is what removes it from the subset, and the queue then empties. (s37-security-signoff.spec.ts)
- [x] A wrongly-classified security tool can be **overturned** by naming which of prevent / detect / respond it serves; the overturn also clears the sign-off so a stale confirmation cannot re-exclude it later. (s37-security-signoff.spec.ts)
- [x] "Mark security-related" stays disabled until a function is named — a capability serving none of the three is not a claim the mapping can act on, and the API rejects it 422. (s37; test_tech_debt_security_classification.py)
- [x] An **unclassified** row (pre-0038, or a provider that omitted the field) is treated as in-scope, never as a negative. Collapsing the two would drop an entire pre-migration inventory out of ATT&CK. (test_tech_debt_security_scope.py, test_tech_debt_security_classification.py)
- [x] A DISCARDED capability list's rows are no longer offered to the ATT&CK mapping. Before this there was no status filter at all, so a thrown-away draft stayed citable forever. (test_tech_debt_security_classification.py)
- [ ] Live path: confirm a **real** provider classifies a mixed portfolio sensibly (the fixture classifies deterministically by row index). Needs a human with a real key.

## 38. Derived six-stage progress (D-040)

- [x] All four workspaces render the same six stages — prepare, analyze, review, approve, generate, release — from a read-only derivation that changes no status. (s38-progress-stages.spec.ts)
- [x] Stage evidence is scoped to the **version that produced it**: an AI run belonging to an earlier draft does not mark a newer one analysed. `llm_calls` carries no version link, so this is the whole point of the derivation. (test_service_stages.py; s38 drives a real discard-and-re-extract cycle)
- [x] No completed stage ever follows an incomplete one, and exactly one stage is current. A cursor sitting behind finished work reads as a broken step rather than a passed one. (test_service_stages.py; s38 asserts the invariant over the whole bar)
- [x] A service with **no version at all** shows nothing as prepared — an empty Tech Debt service must not claim its inventory was uploaded. (test_service_stages.py)
- [x] Zero Trust and CSF label the first stage "Self-assessment"; Tech Debt and ATT&CK call it "Prepare", because they have no client-input step. No stage is rendered permanently dead. (s38-progress-stages.spec.ts; ProgressStages.test.tsx)
- [x] Each stage states its status in text, not colour alone — a progress indicator whose entire meaning is dot colour conveys nothing to a screen reader. (ProgressStages.test.tsx; s38 asserts the rendered text)

## 39. Extraction reconciliation + excluded-row queue (UX finding 4)

- [x] The workspace states what the upload contained, what was kept and what was dropped — "4 rows received · 3 included · 1 excluded" — instead of presenting the survivors as the whole inventory. (s39-excluded-rows.spec.ts)
- [x] Received always equals included plus excluded; recovering a dropped row moves it into the list without changing the received count. (s39-excluded-rows.spec.ts)
- [x] A row the extractor could not interpret can be **named by a consultant** and pulled back in as a real capability, carrying no AI confidence badge. (s39-excluded-rows.spec.ts; test_tech_debt_routes.py)
- [x] Confirming an exclusion **leaves it listed** rather than hiding it — the reconciliation has to keep telling the truth about what was uploaded — but stops flagging it as outstanding. (s39-excluded-rows.spec.ts)
- [x] This is reachable offline at all only because the fixture extractor now skips rows it cannot name, which is what the real prompt instructs. It previously invented a name for every row, so `excluded_rows` was always empty and this entire surface was untestable. (app/ai/fixtures.py; s39)

## 40. Intake: primary contact + shared service defaults (D-041)

- [x] Title, phone and timezone typed on the contact step **survive leaving and returning**. They were previously passed to the step as hardcoded nulls, so the API saved them and the form showed them blank. (browser-verified 2026-08-06 on a fresh account; no committed spec yet)
- [x] "I am not the primary contact" records someone else's details, and the server resolves the engagement's contact to that person. (test_intake_primary_contact.py; browser-verified `is_override: true` end to end)
- [x] An override must name someone — a stray title or phone redirects nothing; a named contact without an email keeps the account address; partial overrides fall back field by field; unchecking clears the stored values. (test_intake_primary_contact.py, 7 cases, verified by breaking the rule)
- [x] Shared deadline and context fan out to the services that have none, filling **blanks only** so a deliberately-set per-service value survives. (SharedServiceDefaults.test.tsx)
- [x] Per-service cards collapse, but any service still missing a required assessment target stays open — a collapsed card hiding a blocking field would look complete and fail at submit. (Step5Notes.tsx; no committed spec yet)
- [ ] An e2e spec walking the intake wizard end to end with an override and shared defaults. The current coverage is unit + a scripted browser run, not a committed spec.

## 41. Admin queue: stage progress + bulk workspace creation (D-040, UX finding 15)

- [x] Each published service in the intake queue shows the same six-stage bar the workspace shows, from the same derivation — the queue cannot drift from the workspace. (browser-verified 2026-08-06; no committed spec yet)
- [x] A service with no workspace yet says "No workspace yet" rather than borrowing a stage word for a state that has no version behind it. (browser-verified 2026-08-06)
- [x] Select-all creates every missing workspace in one action, and the button names the count it will create. (browser-verified: 2 selected → "Create 2 selected workspaces" → both opened)
- [x] A partial run **names what failed** and leaves the failures selected for a one-click retry — reporting "3 created" while two silently did not is the failure bulk creation exists to prevent. (BulkPublishBar.tsx; not yet exercised by a test — the failure path needs a fault-injecting spec)
- [ ] An e2e spec for the queue bar and bulk creation. Browser-verified only.

---

## Sign-off

- [ ] All core flows pass
- [ ] Documents look right
- [ ] No cross-tenant leak
- [ ] No stack traces in `api` logs
- [ ] **Ready for prod**
