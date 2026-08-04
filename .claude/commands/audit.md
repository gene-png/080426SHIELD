---
description: Full security audit — npm vulnerability scan, hardcoded secret detection, and OWASP Top 10 check against the codebase. Run before shipping or on any session where dependencies changed.
allowed-tools: Read, Bash(npm audit:*), Bash(git log:*), Bash(grep:*), Bash(find:*)
---

Run a full security audit across three areas. Use subagents to run all three in parallel, then consolidate.

---

## Agent 1 — Dependency Vulnerabilities

Run both (pnpm monorepo at root, separate npm package in `e2e/`):
```bash
pnpm audit --json
cd e2e && npm audit --json
```
Also `pip-audit` inside the api container if Python dependencies changed.

Parse and report:
- Count of critical, high, medium, low vulnerabilities
- For each **critical** or **high**: package name, vulnerability description, affected versions, and the fix command
- Whether `npm audit fix` can resolve them automatically or if manual intervention is needed

If no vulnerabilities: say so plainly.

---

## Agent 2 — Hardcoded Secrets & Sensitive Data

Scan all source files (excluding `node_modules/`, `.git/`, `playwright-report/`) for patterns that suggest hardcoded secrets:

```bash
grep -rn \
  -e "api_key\s*=\s*['\"][^'\"]" \
  -e "apikey\s*=\s*['\"][^'\"]" \
  -e "secret\s*=\s*['\"][^'\"]" \
  -e "password\s*=\s*['\"][^'\"]" \
  -e "token\s*=\s*['\"][^'\"]" \
  -e "private_key" \
  -e "sk-[a-zA-Z0-9]{20,}" \
  -e "Bearer [a-zA-Z0-9\-_]{20,}" \
  --include="*.ts" --include="*.tsx" --include="*.js" --include="*.json" --include="*.py" --include="*.env*" \
  . 2>/dev/null | grep -v "node_modules" | grep -v ".git"
```

Known-intentional demo/test constants (`DemoPass!2026`, `.env.example` dev creds) are NOT findings — flag anything else.

Also check:
- Is `.env` in `.gitignore`? Read `.gitignore` to confirm.
- Are there any `.env` files committed to the repo? (`git log --all --full-history -- "**/.env"`)

Report every match with file and line number. False positives (like `process.env.API_KEY`) are fine — flag them as safe but include them so I can verify.

---

## Agent 3 — OWASP Top 10 Code Review

Read the source under `apps/api/app/` and `apps/web/src/` (scope to changed files when the diff is small) and check for patterns associated with the OWASP Top 10. For each category, give a **PASS**, **FAIL**, or **REVIEW NEEDED** with specific file and line references:

**A01 — Broken Access Control**
- Are there any routes or API calls with no authentication check?
- Are user-supplied IDs used to access data without verifying ownership?

**A02 — Cryptographic Failures**
- Is any sensitive data stored or transmitted unencrypted?
- Are weak algorithms referenced? (`md5`, `sha1`, `DES`, `RC4`)
- Are passwords stored as plaintext or with weak hashing?

**A03 — Injection**
- Are user inputs ever passed directly into: SQL queries, shell commands (`exec`, `spawn` with user input), `eval()`, HTML without sanitization?
- Are template literals used to construct queries?

**A04 — Insecure Design**
- Are there any features that bypass security checks in development mode that could accidentally reach production?

**A05 — Security Misconfiguration**
- Are debug modes, verbose error messages, or stack traces exposed to end users?
- Are CORS settings overly permissive (`*`)?
- Are default credentials or example keys present?

**A06 — Vulnerable and Outdated Components**
- Summarise findings from Agent 1 in this context.

**A07 — Identification and Authentication Failures**
- Are session tokens short, predictable, or stored insecurely (e.g., in `localStorage` for sensitive apps)?
- Is there any brute-force protection on login flows?

**A08 — Software and Data Integrity Failures**
- Are there any `eval()` calls or dynamic `require()`/`import()` with user-controlled paths?

**A09 — Security Logging and Monitoring Failures**
- Are authentication events (login, logout, failed login) logged?
- Are errors logged with enough context to detect an attack pattern?

**A10 — Server-Side Request Forgery (SSRF)**
- Are there any features that fetch a user-supplied URL server-side without validation?

---

## Consolidated Report

After all three agents complete, produce:

```
## Security Audit Report

### Dependency Vulnerabilities
[Summary + critical/high items]

### Hardcoded Secrets
[Findings or "none found"]

### OWASP Top 10
| # | Category | Status | Notes |
|---|----------|--------|-------|
| A01 | Broken Access Control | PASS/FAIL/REVIEW | ... |
...

### Action Required
[Ordered list of things that must be fixed before shipping, most critical first]

### Recommended (non-blocking)
[Things worth improving but not blockers]
```

**Do not auto-fix anything.** Security issues require human review before changes are made. Present findings, wait for my direction.
