# 2026-09-25: the access-token lifetime stops being stated as fixed (#519)

Branch `track1/session-ttl-prose`, branch-start base `0dcc599`.

#519 filed four prose residuals from the final review of #517. Each was read
against `main` before anything changed:

| #519 item | State on `main` at `0dcc599` | Action |
| --- | --- | --- |
| 1. `BUILD_REPORT.md` A07 reads as a current PASS | Already pinned "as of v3.3.0", pointing at D-085, by #517's own squash commit `59484a9` | none |
| 2. `app/security/jwt.py` docstring: "short-lived access tokens (15 min)" | Live. `config.py` defaults `jwt_access_ttl_seconds` to 3600; compose and `.env.example` set 900 | fixed |
| 3. README: the 60-second grace overstated | Already says only the immediately previous token is honoured, for 60 seconds (`59484a9`) | none |
| 4. `docs/security.md` intro: the 15-minute token "never existed" | Live, and contradicts the body, which says it holds under compose | fixed |

The `jwt.py` docstring now says what the spec asks for and what ships, in
the same form as its twin in `routes/auth.py`. The `docs/security.md` intro now
says the token lifetime was 15 minutes only where it is set to 900 (compose
and `.env.example`), that KMS is wired but unconfigured, and that the other
listed controls did not exist at all. Review round 1 also corrected the
docstring's claim that the signing secret comes from a secrets manager.

Sweep: `grep -rn "15 min" apps/api/app` found one other hit, in
`models/user.py`. It is the lockout window ("10 failed attempts in 15 min"),
which is correct.
