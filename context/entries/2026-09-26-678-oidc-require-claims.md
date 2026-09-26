# 2026-09-26: the Keycloak verifier actually requires exp, iat and sub (#678)

Branch `track2/oidc-require-claims`, from `main` at `c39e6c8`.

- **What was wrong.** `verify_access_token` passed
  `options={"require": [...]}`, which python-jose 3.5 ignores. That was
  measured, not assumed: the list form accepted a token with no `sub`, and
  `require_sub` rejected it. A Keycloak-signed token with no `sub` became a
  KeyError 500 in the exchange route. **Worse than the issue said:** one with
  no `exp` was accepted too, so it never expired. So was one with no `iat`.
- **The fix.** `require_exp`, `require_iat` and `require_sub`. The docstring,
  the 401 message and the route comment now say what is enforced and where it
  is pinned.
- **The test.** A parametrized test through `/auth/oidc/exchange` drops each
  claim and expects a typed 401. It was red first (200, 200, KeyError), and red
  again with the old option put back.
- **The twin.** `security/jwt.py` has the same inert form. Open PR #670
  already fixes it, so this PR leaves that file alone.
- **Round 1 added `require_aud`.** jose's audience check returns early when
  `aud` is absent, so a token with no audience was accepted. The shipped realm
  sets `aud`, so this was unreachable today, but the fix has the same shape.
  The test covers `aud` too. Filed: #688 (a present-but-null `exp` or `iat`,
  an unpinned jose, and the `jwt.py` twin until #670 lands).
