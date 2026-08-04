# Security

This document is the security posture and reporting policy for SHIELD by Kentro v2.0. The detailed threat model, OWASP Top 10 evidence, and audit-walk procedures live in [`docs/security.md`](docs/security.md).

## Reporting a vulnerability

Email `security@kentro.local` with a description, reproduction steps, and impact analysis. Do NOT open a public GitHub issue for security reports.

## Security posture (v1)

| Control                         | Status                                                  | Notes                                                                                    |
| ------------------------------- | ------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| TLS 1.2+ on all transport       | Required                                                | TLS 1.3 preferred at the load balancer                                                   |
| PII redaction on every LLM call | **Mandatory**                                           | Security boundary; never bypassed. Audit row written for every call. See Master Spec §12 |
| Authentication                  | Email + password                                        | MFA + email verification feature-flag-gated, **deferred for v1**                         |
| Session lifetime                | 15 min access JWT / 30 min idle / daily forced re-auth  | Compensating controls for deferred MFA                                                   |
| Account lockout                 | 10 failed attempts in 15 min                            |                                                                                          |
| Audit log                       | Append-only, DB-trigger backed                          | Every state change writes a row                                                          |
| Secrets                         | Env-only (gitignored `.env`) or secrets manager in prod | Never in source                                                                          |
| Stack traces                    | Never surfaced to end users                             | Global exception handler returns correlation ID only                                     |
| OWASP Top 10 (2021)             | Per-commit review per AI Prompt §5.1                    | See `docs/security.md` for current matrix                                                |
| Accessibility                   | WCAG 2.1 AA target                                      | axe-core / Pa11y enforced in CI                                                          |

## Risk acceptances (v1)

Both explicitly accepted by Eugene in Master Spec §2:

1. **Commercial LLM provider may not be FedRAMP-authorized.** Egress may leave the FedRAMP boundary when `SHIELD_LLM_PROVIDER` is set to a commercial endpoint. Mandatory PII redaction is the primary compensating control. Operators targeting FedRAMP boundary posture must set `SHIELD_LLM_PROVIDER` to a FedRAMP-authorized backend (e.g. Azure OpenAI Government, AWS Bedrock-with-Claude in GovCloud); no code changes required.
2. **MFA and email verification deferred.** Compensating controls listed in the table above. Flipping `SHIELD_AUTH_REQUIRE_MFA=true` and `SHIELD_AUTH_REQUIRE_EMAIL_VERIFY=true` activates both flows in v1.x with no code changes.

## Forbidden patterns (pulled from AI Prompt §6)

- No hardcoded LLM provider, model name, or API endpoint.
- No LLM call without passing through the redactor.
- No stack traces to end users.
- No raw JSON in any user-facing UI.
- No secrets in source control, even as placeholders.
- No `--no-verify` bypasses without a documented follow-up fix.
- No mocked redactor "just for testing."
- No internal slug / enum values exposed in UI copy.

## Pre-commit gates

Every commit must pass `pre-commit run --all-files`. Hooks (see `.pre-commit-config.yaml`):

- `gitleaks` — secret scanning
- `ruff` — Python lint
- `black` — Python format
- `mypy` — Python type-check (strict on `apps/api/app/*`)
- `eslint` — TS/JS lint
- `prettier` — TS/JS format
- `pytest -m unit` — API unit tests
- `bandit` — Python security lint

CI re-runs the same set plus integration and E2E.
