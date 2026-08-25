# Security

> Authoritative spec: [`reference-docs/SHIELDv2_Master_Spec.txt`](../reference-docs/SHIELDv2_Master_Spec.txt) §12. AI Prompt §§ 5, 6 are also load-bearing.

> **Honest split, on the model of [`docs/operations.md`](operations.md).**
> Nothing below is written in the present tense unless the code backs it, and the
> evidence column says where.
>
> Status vocabulary, because the two-value version this document started with was
> not enough to be accurate:
>
> - **Implemented** — exists and does what the row says.
> - **Partial** — exists, with a named gap in the evidence cell.
> - **Implemented, tuned for tests** — exists, but its shipped defaults were
>   chosen for the test suite rather than for an attacker.
> - **Not as described** — a control exists but not the one previously claimed.
> - **Dead code** — the implementation exists and nothing calls it.
> - **Fails open** — works until its dependency is unavailable, then permits.
> - **Not implemented** / **Planned — not implemented** — does not exist.
>
> This document previously stated TLS, KMS-encrypted storage, signed CI
> artifacts, a server-side MIME sniff, an HIBP top-100k password check, a
> payload hash on the audit row, and a 15-minute access token. None of those
> existed. A security document that claims controls the code does not have is
> worse than one that claims nothing: it is the artifact an assessor or a client
> reads, and every wrong row in it is a finding waiting to be raised against us.

## Threat model (v1)

| Asset                              | Threat                              | Control                                             | Status                           | Evidence / gap                                                                                                                                                                                                                                                                                                                                                                                              |
| ---------------------------------- | ----------------------------------- | --------------------------------------------------- | -------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Client engagement data in Postgres | Unauthorized read/write             | Role checks at the route layer; audit log           | **Implemented**                  | `app/routes/*` dependencies; `audit_events` table                                                                                                                                                                                                                                                                                                                                                           |
| Client engagement data in Postgres | Unauthorized read/write             | Deployment-isolated DB                              | **Not implemented**              | One Compose database; isolation is a deployment decision and there is no deployment                                                                                                                                                                                                                                                                                                                         |
| Deliverable artifacts in S3        | Exfiltration                        | Authenticated proxy download, tenant + release gate | **Implemented**                  | `app/routes/artifacts.py:204-248` (D-025) — bytes are served by the API after `is_uploader or is_staff or is_released_deliverable`                                                                                                                                                                                                                                                                          |
| Deliverable artifacts in S3        | Exfiltration                        | Signed URLs, short TTL                              | **Dead code**                    | `signed_url` exists (`storage/base.py:40`, `s3.py:63`, `local.py:52`) with **zero callers** anywhere. The 600s default is unreachable. Previously credited here as the implemented control                                                                                                                                                                                                                  |
| Deliverable artifacts in S3        | Exfiltration                        | KMS encryption at rest; bucket policy               | **Not implemented**              | MinIO in Compose; no KMS, no bucket policy                                                                                                                                                                                                                                                                                                                                                                  |
| Session tokens                     | Replay / theft                      | Cookie hardening                                    | **Not as described**             | The API is a **bearer-token** service — `apps/api` sets no cookie at all. The only repo-authored cookie is the tenant selector (`apps/web/src/app/api/active-client/route.ts:43`), `httpOnly` + `sameSite: "lax"`. The Auth.js session cookie uses next-auth defaults (also `lax`). Nothing sets `SameSite=Strict`                                                                                          |
| Session tokens                     | Replay / theft                      | Daily forced re-auth                                | **Implemented**                  | `shield_forced_reauth_seconds` (86400), enforced `app/routes/auth.py:638`, test-covered                                                                                                                                                                                                                                                                                                                     |
| Session tokens                     | Replay / theft                      | Short access-token lifetime                         | **Partial**                      | `jwt_access_ttl_seconds` defaults to **3600**, not the 900 this doc used to claim                                                                                                                                                                                                                                                                                                                           |
| Session tokens                     | Replay / theft                      | Idle timeout                                        | **Not implemented**              | `shield_idle_timeout_seconds` is defined (`config.py:164`) and **read by nothing**                                                                                                                                                                                                                                                                                                                          |
| LLM egress                         | PII leakage to non-FedRAMP provider | Mandatory redactor on every call                    | **Partial**                      | `app/ai/redact.py` is the single egress path and no production call site skips it. But `SHIELD_REDACTION_MODE=off` **is** a skip, refused only on `production` (#142), and `LLMClient` accepts a per-call `redaction_mode` override (`ai/llm.py:573`) that no audit row records (#144)                                                                                                                      |
| LLM egress                         | PII leakage to non-FedRAMP provider | Audit row records what the redactor removed         | **Partial**                      | `llm_calls.redacted_counts`; six known defects make a count wrong in both directions — see below                                                                                                                                                                                                                                                                                                            |
| Brute force / credential stuffing  | Account takeover                    | Per-IP and per-account rate limiting                | **Implemented, tuned for tests** | `app/security/rate_limit.py`, on by default (`shield_rate_limit_enabled`), enforced `app/routes/auth.py:501` before the Argon2 verify. **Shipped defaults are 300/min per IP and 100/min per account** — `config.py:167-171` says they are deliberately generous so the serialized e2e suite never trips them. At those values the effective brute-force control is account lockout (10 / 15 min), not this |
| Brute force / credential stuffing  | Account takeover                    | Rate limiting survives a Redis outage               | **Fails open**                   | `rate_limit.py:110-112` logs loudly and returns — a Redis outage removes brute-force protection platform-wide. Account lockout is the second line                                                                                                                                                                                                                                                           |
| Account enumeration                | Valid-email discovery               | Dummy-hash timing equalisation                      | **Implemented**                  | `app/routes/auth.py:508-515` — a precomputed Argon2 hash is verified on the unknown-email path so timing does not distinguish                                                                                                                                                                                                                                                                               |
| Credentials in source              | Accidental commit                   | gitleaks + `detect-private-key` pre-commit, CI scan | **Implemented**                  | `.pre-commit-config.yaml:13,20`; CI `Secret scan` job                                                                                                                                                                                                                                                                                                                                                       |
| Supply chain                       | Malicious dependency                | `pnpm audit` + `pip-audit` in CI; Dependabot        | **Partial**                      | Both run with `continue-on-error: true` — they report, they cannot fail a build                                                                                                                                                                                                                                                                                                                             |
| File uploads                       | Malicious payload                   | Size cap                                            | **Implemented**                  | `MAX_UPLOAD_BYTES`, `app/routes/artifacts.py`                                                                                                                                                                                                                                                                                                                                                               |
| File uploads                       | Malicious payload                   | MIME allow-list                                     | **Partial — see gap**            | `app/routes/artifacts.py:100` trusts `file.content_type`, the **client-supplied** header                                                                                                                                                                                                                                                                                                                    |
| File uploads                       | Malicious payload                   | Server-side content sniff; AV scan; quarantine      | **Not implemented**              | Bytes are never inspected                                                                                                                                                                                                                                                                                                                                                                                   |

**The upload row is the one to read twice.** The allow-list is checked against
the `Content-Type` the client sends, and the file is then stored under that
declared type. A payload announcing `application/pdf` passes whatever its bytes
are. This was previously written as "server-side MIME sniff", which describes a
control that would catch exactly that and does not exist.

## OWASP Top 10 (2021)

### Implemented, with evidence

| ID  | Category                       | What exists                                                                                                                                                                                                                                                                                                                                                                                                             |
| --- | ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A01 | Broken Access Control          | Role-based route guards and an audit log (landed Phase 1; this row previously still said "Pending Phase 1")                                                                                                                                                                                                                                                                                                             |
| A02 | Cryptographic Failures         | **Passwords only** — Argon2id, `app/security/password.py`. Transport and at-rest encryption are in the next table                                                                                                                                                                                                                                                                                                       |
| A03 | Injection                      | SQLAlchemy parameterized queries; no raw SQL in app code                                                                                                                                                                                                                                                                                                                                                                |
| A04 | Insecure Design                | This threat model; adversarial review recorded on every code PR (D-054/D-057)                                                                                                                                                                                                                                                                                                                                           |
| A05 | Security Misconfiguration      | `ENVIRONMENT=production` suppresses `/docs` and `/openapi.json` (`main.py:64,66`) and arms two boot refusals (`config.py:301,306`). **On `staging` all four are off** — the interactive Swagger UI and the full OpenAPI schema are published (#142). Six response headers in `apps/web/next.config.mjs`: CSP, HSTS, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy` |
| A06 | Vulnerable Components          | Dependabot; `pnpm audit` + `pip-audit` in CI (non-blocking)                                                                                                                                                                                                                                                                                                                                                             |
| A07 | Identification & Auth Failures | TOTP MFA and email verification implemented (Sprint 6, D-027/D-028), enforcement flag-gated and default off; per-IP + per-account rate limiting (default on, disableable via `shield_rate_limit_enabled`, and tuned generously for the e2e suite) and account lockout (no flag, always on)                                                                                                                              |
| A09 | Logging + Monitoring           | Structured JSON logs (structlog) with correlation IDs; `audit_events`; `llm_calls` ledger                                                                                                                                                                                                                                                                                                                               |
| A10 | SSRF                           | LLM endpoint is env-configured only; no user-supplied URLs reach a fetch                                                                                                                                                                                                                                                                                                                                                |

**A05, stated precisely, because the previous wording was wrong in both
directions.** It said "CSP + HSTS at edge". There is no edge — these are Next.js
response headers — but there are also four more headers than it credited.

The CSP is genuinely restrictive where it counts: `default-src 'self'`,
`frame-ancestors 'none'`, `object-src 'none'`, `base-uri 'self'`,
`form-action 'self'`, and no remote origin permitted anywhere. **Its one real
weakness is `script-src 'self' 'unsafe-inline' 'unsafe-eval'`**, which is
deliberate (Next's bootstrap and Tailwind's inline styles need it) and which
means the policy does **not** stop injected inline script — the primary thing a
CSP exists to stop. Treat it as strong against remote-origin exfiltration and
clickjacking, weak against reflected/stored XSS.

HSTS is **inert today**: browsers ignore `Strict-Transport-Security` delivered
over plain HTTP, and there is no TLS. The header is set and currently does
nothing.

### Planned — not implemented

Nothing in this table exists in the repo. Most of it is gated on the cloud,
account, region and network decisions tracked as **needs-David** in
[`DELIVERY_PLAN.md`](../DELIVERY_PLAN.md); `infra/terraform/` is an empty
placeholder and `docs/runbooks/` is empty.

| ID  | Category                           | Not implemented                                                                         |
| --- | ---------------------------------- | --------------------------------------------------------------------------------------- |
| A02 | Cryptographic Failures             | TLS anywhere (Compose is plain HTTP); AES-256 + KMS for data at rest                    |
| A05 | Security Misconfiguration          | An edge/CDN tier to terminate TLS and enforce HSTS meaningfully                         |
| A06 | Vulnerable Components              | A blocking dependency gate — both audits are `continue-on-error`                        |
| A08 | Software + Data Integrity Failures | Subresource integrity; signed CI artifacts; any release signing. There is no deployment |
| A09 | Logging + Monitoring               | Alerting, log aggregation, and a metrics endpoint (none exists to scrape)               |
| —   | Package                            | FedRAMP artifacts (SSP / SAR / POA&M)                                                   |

## Redaction (Master Spec §12 — primary control)

`app/ai/redact.py` is the single LLM egress path and is treated as a security
boundary. In `strict` mode it runs **ten** passes: signature block, email, SSN,
EIN, contract number, phone, CAGE, name hints, address, org name. `standard`
runs the first eight — address and org name are strict-only.

**Implemented:**

- Every call site flows through the redactor. There is no per-call skip.
- `SHIELD_REDACTION_MODE=off` is refused when `ENVIRONMENT=production`
  (`app/config.py:301`). **It is NOT refused on `staging`** — the guard keys on
  `is_production()` and `Environment` has three members, so a staging
  deployment boots with the entire redactor disabled and every `llm_calls` row
  recording an empty `redacted_counts`, indistinguishable from a run with
  nothing to remove. Filed as **#142**; the sibling `jwt_signing_secret` guard
  on the next line has the identical hole.
- The address rule is decided by an enumerated truth table
  (`apps/api/tests/unit/test_redact_address_matrix.py`, 327 cells) rather than a
  regex patched case by case — see **D-058**.
- Counts of what was removed are written to `llm_calls.redacted_counts`
  (`app/ai/llm.py:607`). **`artifact_redactions.removed_items` does not exist** —
  no model, no migration, no writer. It is a Master Spec §11 aspiration that
  reached this document through a stale docstring in `app/ai/redact.py:15`.

**Known defects in this control, all filed and all `mvp-blocking`.** Three are
leaks and three corrupt or misreport. They are listed here rather than left to
the issue tracker because this is the document that describes the control:

| Issue | Defect                                                                                                                                                                                                                                                                  |
| ----- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| #135  | A line reading `Thanks` / `Best` / `Regards` truncates everything after it, and the run records a successful redaction                                                                                                                                                  |
| #136  | `_RE_CONTRACT` has no `IGNORECASE`, so a lowercase contract number egresses whole                                                                                                                                                                                       |
| #137  | `_RE_CAGE` misses `CAGE Code <n>`, matches an empty separator, and rewrites the phrase "CAGE codes" while recording a removal that did not happen                                                                                                                       |
| #138  | Spelled-out and alphanumeric house numbers are not matched (`221B Baker Street`, `One Federal Plaza`)                                                                                                                                                                   |
| #139  | `Building`, `Bldg`, `Rm`, `Room`, `Level`, `Mail Stop` match nothing                                                                                                                                                                                                    |
| #140  | `_RE_PHONE` turns `Segments 10.20.30.40 and 10.20.30.41 are isolated.` into `Segments [PHONE] and [PHONE] are isolated.`, recording `phone: 2` over text containing no phone number. Space-separated digit runs of 10-20 characters match; comma-separated lists do not |

**Corrections to what this section used to say.** It cited a test path that does
not exist (`apps/api/tests/unit/ai/test_redact.py`; the real files are
`tests/unit/test_redact.py` and `tests/unit/test_redact_address_matrix.py`), and
it claimed the audit row carries "a hash of the redacted payload". There is no
hash column on `llm_calls` — it stores counts and nothing else.

## Authentication (v1) — email + password

**Implemented:**

- Argon2id hashing (`app/security/password.py`).
- Minimum password length 12, maximum 256.
- Account lockout: 10 failed attempts in 15 minutes
  (`shield_account_lockout_max_attempts`, `shield_account_lockout_window_seconds`).
- Refresh-token rotation with a 60s grace window for concurrent callers.
- Daily forced re-auth (`shield_forced_reauth_seconds`, 86400).
- TOTP MFA (RFC 6238, `app/security/totp.py`, D-027) and email verification /
  password reset (`app/email/`, D-028). Enforcement is flag-gated and
  **default-OFF** (`SHIELD_AUTH_REQUIRE_MFA`, `SHIELD_AUTH_REQUIRE_EMAIL_VERIFY`);
  turning them on is a deploy-time choice with no code change.

**Not implemented, and previously claimed:**

- **Breached-password screening.** This document said "not in HIBP top-100k".
  The actual check is a **three-entry deny list** — `password1234`,
  `letmein12345`, `qwertyuiopas` — under a comment in `app/security/password.py`
  reading "A full HIBP top-100k check belongs in a Phase 6 hardening pass". The
  deny list exists so dev fixtures fail policy, not as a breach corpus.
- **15-minute access tokens.** `jwt_access_ttl_seconds` defaults to **3600**.
  The old text named `JWT_ACCESS_TTL_SECONDS=900`, a value the config does not
  hold.
- **Idle timeout.** `shield_idle_timeout_seconds` is defined and read by nothing.

## Pre-commit and CI gates

Pre-commit (`.pre-commit-config.yaml`): gitleaks, `detect-private-key`, ruff,
ruff-format, black, **mypy**, bandit, plus whitespace/JSON/YAML hygiene.

CI runs in **two** workflow files, not one:

- `.github/workflows/ci.yml` — Python (`ruff`, `black --check`, `bandit`,
  `pytest -m unit`, plus three static sweeps: `check_test_integrity`,
  `check_no_control_chars`, and `check_plan_totals`); Web (`eslint`, `prettier`, `tsc --noEmit`, `vitest`,
  `next build`); E2E (Playwright smoke, including `axe-core` at
  `e2e/smoke/s16-axe.spec.ts`); Demo (hosted-demo reset + journey spec); and the
  gitleaks secret scan.
- `.github/workflows/audit-gate.yml` — adversarial-audit evidence and the
  accidental-issue-close guard.

**The seven required status checks on `main`**, read from the API on 2026-08-25:
Python, Web, E2E, Demo, Secret scan, Adversarial audit recorded, No accidental
issue closes.

**`mypy` runs in pre-commit only — CI does not run it.** This section previously
listed it among the CI gates without that distinction. Note also that branch
protection has `enforce_admins: false`, so both developers can merge past every
check above; see `DELIVERY_PLAN.md` for the full branch-protection posture.

## Incident response

**Not implemented.** `docs/runbooks/` contains only `.gitkeep`. There is no
on-call rotation, no paging integration, and no post-mortem process — earlier
text here named PagerDuty "configured per engagement", which was never true, and
deferred runbooks to "Phase 6", which has passed.

What exists to investigate with: structured JSON logs with correlation IDs
(`docker compose logs -f api`), the `audit_events` table, and the `llm_calls`
ledger. Runbooks needed before a real engagement: incident response,
backup/restore, key rotation, DR, and redactor-failure.

## Reporting a vulnerability

See [`SECURITY.md`](../SECURITY.md) at the repo root.

---

When any row above moves from planned to implemented, move it into the
implemented table **with the path or command that proves it** — the same rule
`docs/operations.md` closes with.
