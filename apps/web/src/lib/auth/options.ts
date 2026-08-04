/**
 * Auth.js (next-auth v5) configuration: a Credentials provider hitting the
 * FastAPI /auth/login endpoint and storing the returned access + refresh
 * tokens in the encrypted JWT session.
 *
 * v5 migration (Sprint 7 T5): this module now owns the `NextAuth()` call and
 * exports the universal `{ handlers, auth, signIn, signOut }`. Server code
 * calls `auth()` in place of the v4 `getServerSession(authOptions)`; the
 * `[...nextauth]` route re-exports `handlers`. Client components still import
 * `signIn`/`signOut`/`useSession` from `next-auth/react` (unchanged in v5).
 *
 * v1.x will swap the Credentials provider for a Keycloak OIDC provider with the
 * same `aud=shield-api` claim - no schema migration required.
 */

import NextAuth, { CredentialsSignin, customFetch } from "next-auth";
import type { NextAuthConfig, User } from "next-auth";
import type { JWT } from "next-auth/jwt";
import Credentials from "next-auth/providers/credentials";
import Keycloak from "next-auth/providers/keycloak";

import { ApiError, apiFetch } from "@/lib/api";
import { OIDC_EXCHANGE_ERROR, REAUTH_REQUIRED_ERROR } from "@/lib/auth/errors";
import { isOidcEnabled, keycloakFetch } from "@/lib/auth/oidc";

interface LoginResponse {
  access_token: string | null;
  refresh_token: string | null;
  access_expires_at: string | null;
  refresh_expires_at: string | null;
  // MFA challenge branch (Sprint 6 T4, D-027). When the user has TOTP MFA
  // enrolled, /auth/login returns mfa_required=true + a short-lived pending
  // token instead of the pair; the pair arrives from /auth/mfa/verify-login.
  mfa_required?: boolean;
  mfa_pending_token?: string | null;
}

/**
 * Thrown out of `authorize` when the password is correct but a TOTP second
 * factor is still required. In v5, a `CredentialsSignin` subclass's `code` is
 * placed in the sign-in redirect URL's `code` query param, which the client's
 * `signIn(..., { redirect: false })` returns as `result.code`. The sign-in
 * form matches this to reveal the authenticator-code field. (In v4 this rode
 * the free-form `result.error` string; v5 normalizes every credentials failure
 * to `error: "CredentialsSignin"`, so the distinguishing signal is `code`.)
 */
class MfaRequiredError extends CredentialsSignin {
  code = "mfa_required";
}

/** Mirrors the backend TokenPairResponse returned by POST /auth/refresh, which
 * always yields a full (non-null) pair — unlike /auth/login, which can return
 * an MFA challenge instead. */
interface RefreshResponse {
  access_token: string;
  refresh_token: string;
  access_expires_at: string;
  refresh_expires_at: string;
}

/** Refresh this many ms early so an in-flight proxy call never races expiry. */
const REFRESH_SKEW_MS = 30_000;

/** Pull the typed `reason` out of the backend's {error:{reason}} envelope. */
function reasonOf(payload: unknown): string | undefined {
  if (payload && typeof payload === "object" && "error" in payload) {
    const err = (payload as { error?: unknown }).error;
    if (err && typeof err === "object" && "reason" in err) {
      const reason = (err as { reason?: unknown }).reason;
      return typeof reason === "string" ? reason : undefined;
    }
  }
  return undefined;
}

/**
 * Trade the stored refresh token for a fresh access+refresh pair.
 *
 * The backend access token lives 15 min while the NextAuth session lives
 * 24 h, so without this the session keeps handing proxies a dead bearer and
 * every upstream call 401s. On failure we stamp the token with an error so
 * `session()` stops exposing the access token and the UI falls back to
 * sign-in. A backend `reauth_required` / `refresh_reused` reason (daily
 * forced-reauth ceiling, or a rotated-out token) is surfaced as the distinct
 * REAUTH_REQUIRED_ERROR so the UI can show friendly "please sign in again"
 * copy rather than a generic error.
 */
async function refreshAccessToken(token: JWT): Promise<JWT> {
  if (!token.refreshToken) {
    return { ...token, error: "RefreshAccessTokenError" };
  }
  try {
    const refreshed = await apiFetch<RefreshResponse>("/auth/refresh", {
      method: "POST",
      body: { refresh_token: token.refreshToken },
      // Refresh is not tenant-scoped; don't leak a cookie-derived X-Client-Id.
      clientId: "",
    });
    return {
      ...token,
      accessToken: refreshed.access_token,
      refreshToken: refreshed.refresh_token,
      accessExpiresAt: refreshed.access_expires_at,
      error: undefined,
    };
  } catch (err) {
    const reason = err instanceof ApiError ? reasonOf(err.payload) : undefined;
    const isReauth =
      reason === "reauth_required" || reason === "refresh_reused";
    return {
      ...token,
      error: isReauth ? REAUTH_REQUIRED_ERROR : "RefreshAccessTokenError",
    };
  }
}

interface MeResponse {
  id: string;
  email: string;
  role: "admin" | "client";
  display_name: string | null;
}

/**
 * Shape of a successful POST /auth/oidc/exchange (backend OidcExchangeResponse,
 * D-032): the matched local user plus a freshly minted SHIELD pair. Only the
 * fields the jwt callback seeds are typed here — the pair mirrors the
 * credentials LoginResponse so downstream expiry/refresh logic is identical.
 */
interface OidcExchangeResponse {
  user: { role: "admin" | "client" };
  tokens: {
    access_token: string;
    refresh_token: string;
    access_expires_at: string;
  };
}

/**
 * The Keycloak (OIDC) provider — registered ONLY when the flag is on. A public
 * client: no secret, PKCE + state, `token_endpoint_auth_method: "none"`. The
 * `customFetch` rewrites Auth.js's server-side discovery fetch from the public
 * (browser-facing localhost) issuer to the container-reachable internal host;
 * after discovery, Keycloak's backchannel-dynamic config already returns
 * internal token/JWKS URLs (Sprint 9 T5), so it is a passthrough thereafter.
 *
 * If a future next-auth beta rejects the secret-less client, the pre-approved
 * fallback (D-032 / SPRINT_9 T6) flips the realm client to confidential and
 * plumbs KEYCLOAK_CLIENT_SECRET here — a dev-realm-only secret, documented as
 * such. This build ships the secret-less client (verified against beta.31).
 */
function keycloakProvider(): ReturnType<typeof Keycloak> {
  return Keycloak({
    clientId: process.env.KEYCLOAK_CLIENT_ID,
    issuer: process.env.KEYCLOAK_ISSUER,
    checks: ["pkce", "state"],
    client: { token_endpoint_auth_method: "none" },
    [customFetch]: keycloakFetch,
  });
}

export const authConfig: NextAuthConfig = {
  session: { strategy: "jwt", maxAge: 60 * 60 * 24 },
  pages: { signIn: "/sign-in" },
  // The dev/CI stack sets NEXTAUTH_SECRET (compose) rather than v5's AUTH_SECRET,
  // and runs behind the next-dev proxy without AUTH_URL — read the secret
  // explicitly and trust the host so the config is env-name-agnostic.
  secret: process.env.AUTH_SECRET ?? process.env.NEXTAUTH_SECRET,
  trustHost: true,
  providers: [
    Credentials({
      name: "Email + password",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
        // Optional second factor. Absent on the first submit; the form re-submits
        // with it after we signal MFA_REQUIRED.
        totp: { label: "Authenticator code", type: "text" },
      },
      async authorize(credentials) {
        const email =
          typeof credentials?.email === "string" ? credentials.email : "";
        const password =
          typeof credentials?.password === "string" ? credentials.password : "";
        const totp =
          typeof credentials?.totp === "string" ? credentials.totp : "";
        if (!email || !password) {
          return null;
        }
        try {
          const login = await apiFetch<LoginResponse>("/auth/login", {
            method: "POST",
            body: { email, password },
          });

          let tokens: LoginResponse = login;
          if (login.mfa_required) {
            // Password was correct but a second factor is needed. Without a code
            // yet, tell the form to prompt for one. With a code, exchange the
            // pending token for the real pair.
            if (!totp) {
              throw new MfaRequiredError();
            }
            tokens = await apiFetch<LoginResponse>("/auth/mfa/verify-login", {
              method: "POST",
              body: {
                mfa_pending_token: login.mfa_pending_token,
                code: totp,
              },
            });
          }

          if (!tokens.access_token || !tokens.refresh_token) {
            return null;
          }
          const me = await apiFetch<MeResponse>("/auth/me", {
            bearer: tokens.access_token,
          });
          const user: User = {
            id: me.id,
            email: me.email,
            name: me.display_name ?? me.email,
            role: me.role,
            accessToken: tokens.access_token,
            refreshToken: tokens.refresh_token,
            accessExpiresAt: tokens.access_expires_at ?? undefined,
          };
          return user;
        } catch (err) {
          if (err instanceof CredentialsSignin) {
            // MFA-required (or any credentials signal) — re-throw so v5 surfaces
            // its `code` to the sign-in form.
            throw err;
          }
          if (
            err instanceof ApiError &&
            (err.status === 401 || err.status === 423)
          ) {
            // Wrong password / locked / wrong-or-expired MFA code → generic.
            return null;
          }
          throw err;
        }
      },
    }),
    // Flag OFF (default): the Keycloak provider does NOT exist — zero discovery /
    // JWKS network requests, every credential surface unchanged. `options.ts` is
    // load-bearing for all ~24 credential e2e specs, so the seam is gated here at
    // provider-registration time, not with runtime branching in the flow.
    ...(isOidcEnabled() ? [keycloakProvider()] : []),
  ],
  callbacks: {
    async jwt({ token, account, user }) {
      // Keycloak (OIDC) initial sign-in — ordered BEFORE the credentials
      // `if (user)` seed because an OIDC sign-in ALSO carries a profile `user`.
      // Trade the Keycloak access token for a SHIELD pair via the backend
      // exchange (D-032); the seeded shape is IDENTICAL to the credentials path,
      // so downstream expiry/refresh/session logic is untouched. On refusal we
      // stamp OIDC_EXCHANGE_ERROR (never seed tokens), which SessionExpiryGuard
      // turns into a loud /sign-in?reason=oidc_exchange_failed redirect.
      if (account?.provider === "keycloak") {
        if (!account.access_token) {
          console.error("[auth.oidc] keycloak sign-in carried no access_token");
          token.error = OIDC_EXCHANGE_ERROR;
          return token;
        }
        try {
          const exchanged = await apiFetch<OidcExchangeResponse>(
            "/auth/oidc/exchange",
            {
              method: "POST",
              body: { keycloak_access_token: account.access_token },
              // Not tenant-scoped; don't leak a cookie-derived X-Client-Id.
              clientId: "",
            },
          );
          token.role = exchanged.user.role;
          token.accessToken = exchanged.tokens.access_token;
          token.refreshToken = exchanged.tokens.refresh_token;
          token.accessExpiresAt = exchanged.tokens.access_expires_at;
          token.error = undefined;
          console.info(
            `[auth.oidc] exchange succeeded role=${exchanged.user.role}`,
          );
          return token;
        } catch (err) {
          const reason =
            err instanceof ApiError ? reasonOf(err.payload) : undefined;
          console.error(
            `[auth.oidc] exchange rejected reason=${reason ?? "unknown"}`,
          );
          token.error = OIDC_EXCHANGE_ERROR;
          return token;
        }
      }
      // Initial sign-in: seed the token from the authorized user.
      if (user) {
        token.role = user.role;
        token.accessToken = user.accessToken;
        token.refreshToken = user.refreshToken;
        token.accessExpiresAt = user.accessExpiresAt;
        token.error = undefined;
        return token;
      }
      // A rejected OIDC exchange is TERMINAL: it seeded no access/refresh token,
      // so the refresh path below would clobber the reason to a generic
      // RefreshAccessTokenError on the very next jwt invocation (the client's
      // /api/auth/session fetch) and SessionExpiryGuard would never route the
      // user to the loud oidc_exchange_failed banner. Preserve it so the guard
      // fires. (Found by the T6 browser spike — a unit mock can't see this
      // multi-invocation sequence.)
      if (token.error === OIDC_EXCHANGE_ERROR) {
        return token;
      }
      // Subsequent calls: keep the access token alive while it's still valid,
      // otherwise rotate it via the refresh token before any proxy reads it.
      const expiresAt = token.accessExpiresAt
        ? Date.parse(token.accessExpiresAt)
        : 0;
      if (expiresAt && Date.now() < expiresAt - REFRESH_SKEW_MS) {
        return token;
      }
      return refreshAccessToken(token);
    },
    async session({ session, token }) {
      session.role = token.role;
      // Don't hand out a token we know is dead; surface the error so the UI
      // can route back to sign-in instead of silently 401ing on every proxy.
      session.accessToken = token.error ? undefined : token.accessToken;
      session.error = token.error;
      return session;
    },
  },
};

export const { handlers, auth, signIn, signOut } = NextAuth(authConfig);
