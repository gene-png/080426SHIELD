# SHIELD v2 — Developer Work Order (Parts A–F)

Implements the full SHIELD v2 Developer Work Order: multi-tenant onboarding, a
single AI engine with four job types, the three service AI loops, the CSF full
Playbook, the greenfield Risk Register, navigation/messaging, and a hardening
pass. Built additively on the existing platform, with deterministic scoring kept
in code and the AI restricted to drafting values + narrative.

**Branch:** `feat/multi-tenant-engagement-flow` → `main`
**Migrations:** `0015`–`0025` (sequential, SQLite-safe via `batch_alter_table`)
**Full versioned log:** `IMPLEMENTATION.md` · **Decisions:** `DECISIONS.md`

---

## What's included

### A — Reconciliation cleanup

- A1 clients can no longer reach deliverables; A2 "engagement" → "assessment";
  A3 reviewer role removed; A4 Zero Trust DoD scale reduced to 3 levels.

### B — Onboarding

- B1 domain-approved registration (first user bootstraps admin; others must match
  an approved `client_domain`); B2 admin client + domain management.

### C — Shared platform

- C0 status vocabulary reconciled (additive). C1 one AI egress
  (`LLMClient.invoke(purpose=…)`) + a job registry (`tech_debt_extract`,
  `mitre_map`, `zt_score`, `csf_score`, `risk_synthesize`) with redaction +
  `llm_calls` logging. C2 lock-skip + a "what-changed" diff on every rerun.
  C3 a `documents_stale` flag (AI run sets it, finalize/export clears it) with a
  regenerate nudge. C4 Word (.docx) export. C5 service dashboards. C6 admin +
  client navigation shells (no dead ends). C7 per-assessment messaging (threads +
  admin inbox + unread). C8 verbatim CSF/ZT interview questions.

### D — Services

- **D1** Tech Debt dashboard. **D2** ATT&CK D/P/R tooling + heatmap + `mitre_map`
  Run-AI. **D3** Zero Trust per-capability current/target + 12-month roadmap +
  `zt_score`. **D4** CSF **full Playbook**: a deterministic engine (totals/levels,
  evidence cap, the six weighted-floor roll-up rules, gap, P1/P2/P3 — 20 unit
  tests), tiered HIGH/MOD/LOW Working Profiles, the Enterprise roll-up, an
  editable per-tier UI, `csf_score`, and exports (XLSX workbook + an executive
  briefing and full playbook, each PDF + Word, with colour-coded maturity cells).

### E — Risk Register (greenfield)

- A 5×5 NIST 800-30 tier engine, a generation gate (ATT&CK **and** (CSF or ZT)),
  `risk_synthesize` with catalog-validated links and **code-derived tiers**,
  versioned registers, XLSX/PDF/Word exports, and an admin dashboard (KPIs +
  heatmap + entries table).

### F — Harden

- Cross-tenant isolation tests for every new table; **synchronous-AI** decision
  (orphaned Celery worker removed); `pip-audit` + `pnpm audit` + Dependabot;
  CSP + the existing security headers; static `jsx-a11y` + skip links in every
  shell; a production web Dockerfile; a documented pluggable auth seam.

---

## Testing & verification

- **Backend:** full `pytest -m unit` suite green (incl. the deterministic-engine
  and isolation suites). AI paths are exercised with the fixture provider.
- **Web:** `next build` compiles + statically generates all 35 pages; `tsc` +
  `eslint` clean.
- **CI-equivalent gates pass locally:** ruff · black · bandit · prettier · tsc ·
  eslint · pytest. (CI runs only on `main`/PRs, so this PR is its first run.)

---

## Deliberate deviations (logged in DECISIONS.md / IMPLEMENTATION.md)

- **C0** implemented additively (no big-bang status rename — `released` was dead).
- **D4 CSF tiered model added alongside** the simplified `CsfAnswer` (which still
  backs the client self-assessment) rather than replacing it, to avoid
  destabilizing the existing flow.
- **IG Core/Supporting cross-reference metadata not imported**, so roll-up Rules
  2/5 and the `is_core` priority use safe defaults until that reference data lands.
- **C3** is a staleness flag (product decision) rather than auto-rendering docs on
  every AI run.

## Out of scope / follow-ups

- `infra/terraform` for AWS GovCloud / Azure Government (needs account/region/network).
- Runtime axe/Pa11y in CI (needs a built-app harness; static a11y is enforced).
- Human pre-prod QA: live browser walkthrough, eyeballing the generated documents,
  and one live-AI (Anthropic) Run-AI.

## How to review

Start with `IMPLEMENTATION.md` (the part-by-part log) and the migrations
`0015`–`0025`. The deterministic engines (`app/csf/playbook.py`,
`app/risk/engine.py`, `app/zt/scoring.py`) and their unit tests are the core of
the "AI suggests, code computes" guarantee.
