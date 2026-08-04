# Security

> Authoritative spec: [`reference-docs/SHIELDv2_Master_Spec.txt`](../reference-docs/SHIELDv2_Master_Spec.txt) §12. AI Prompt §§ 5, 6 are also load-bearing.

## Threat model (v1)

| Asset                              | Threat                              | Primary control                                              | Compensating                                                                |
| ---------------------------------- | ----------------------------------- | ------------------------------------------------------------ | --------------------------------------------------------------------------- |
| Client engagement data in Postgres | Unauthorized read/write             | Row-level role checks at route layer; deployment-isolated DB | Audit log; least-privilege DB role                                          |
| Deliverable artifacts in S3        | Exfiltration                        | Signed URLs with short TTL; KMS-encrypted at rest            | Bucket policy denies anonymous access                                       |
| Session tokens                     | Replay / theft                      | 15-min access JWT, 30-min idle, daily forced re-auth         | HttpOnly + Secure + SameSite=Strict cookies                                 |
| LLM egress                         | PII leakage to non-FedRAMP provider | **Mandatory redactor** on every call                         | Audit row proves redactor ran; provider env-swappable to FedRAMP-authorized |
| Credentials in source              | Accidental commit                   | gitleaks pre-commit; `detect-private-key` hook               | `.env` gitignored; SECURITY.md policy                                       |
| Supply chain                       | Malicious dependency                | `pnpm audit` + `pip-audit` in CI; pinned versions            | Dependabot weekly                                                           |
| File uploads                       | Malicious payload                   | Server-side MIME sniff; size cap; AV scan (Phase 6)          | Quarantine bucket                                                           |

## OWASP Top 10 (2021) - per-commit review process

Every commit message must reference which OWASP category it touches if any. CHANGELOG entries per phase summarize the cumulative posture. The matrix below is filled in across phases.

| ID  | Category                           | v1 status                                                                                                                               |
| --- | ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| A01 | Broken Access Control              | Pending Phase 1 (role-based route guards + audit)                                                                                       |
| A02 | Cryptographic Failures             | TLS 1.2+ everywhere; bcrypt/Argon2 for passwords; AES-256 + KMS for at-rest                                                             |
| A03 | Injection                          | SQLAlchemy parameterized queries only; no raw SQL in app code                                                                           |
| A04 | Insecure Design                    | Threat model in this doc; per-phase review                                                                                              |
| A05 | Security Misconfiguration          | `ENVIRONMENT=production` disables debug; CSP + HSTS at edge                                                                             |
| A06 | Vulnerable Components              | Dependabot + audit hooks                                                                                                                |
| A07 | Identification & Auth Failures     | TOTP MFA + email verification implemented (Sprint 6, D-027/D-028); enforcement flag-gated, default off; compensating controls always on |
| A08 | Software + Data Integrity Failures | Subresource integrity on CDN-free deploys; signed CI artifacts                                                                          |
| A09 | Logging + Monitoring               | Structured JSON logs; correlation IDs; audit log; alerting in Phase 6                                                                   |
| A10 | SSRF                               | LLM endpoint is env-configured only; no user-supplied URLs                                                                              |

## Redaction (Master Spec §12 - primary control)

The redactor in `apps/api/app/ai/redact.py` is treated as a security boundary:

- All call sites flow through the redactor; there is no "skip for this one" path.
- A unit-test suite (`apps/api/tests/unit/ai/test_redact.py`) verifies that emails, phone numbers, SSNs, internal hostnames, organization-specific identifiers, and credential-shaped strings are redacted.
- An audit row is written **before** the LLM call records that the redactor ran (with a hash of the redacted payload, not the payload itself).
- `SHIELD_REDACTION_MODE=off` is rejected outside `ENVIRONMENT=development` at startup.

## Authentication (v1) - email + password

- Argon2id hashing (parameters per OWASP Password Storage Cheat Sheet).
- Password policy: ≥12 characters, not in HIBP top-100k.
- Account lockout: 10 failed attempts in 15 minutes (`SHIELD_ACCOUNT_LOCKOUT_*`).
- Session: 15-minute access JWT (`JWT_ACCESS_TTL_SECONDS=900`), 30-minute idle timeout, daily forced re-auth.
- TOTP MFA (RFC 6238, `app/security/totp.py`, D-027) and email verification / password reset (`app/email/`, D-028) are implemented (Sprint 6). Enforcement is flag-gated and default-OFF (`SHIELD_AUTH_REQUIRE_MFA`, `SHIELD_AUTH_REQUIRE_EMAIL_VERIFY`) — flipping them on is a deploy-time choice with no code changes.

## Pre-commit and CI gates

See `.pre-commit-config.yaml` and `.github/workflows/ci.yml`. Minimum:

- `gitleaks` and `detect-private-key` (secret scanning).
- `ruff` + `black` + `mypy` + `bandit` (Python lint, format, types, security).
- `eslint` + `prettier` + `tsc --noEmit` (TS lint, format, types).
- `pytest -m unit` on every API change.
- `axe-core` accessibility check on every key page (lands with Phase 1 stage 8).

## Incident response

Runbook templates land in `docs/runbooks/` during Phase 6. The v1 process is: page on-call (PagerDuty - configured per engagement), capture correlation IDs from logs, follow runbook, post-mortem within 5 business days.

## Reporting a vulnerability

See [`SECURITY.md`](../SECURITY.md) at the repo root.
