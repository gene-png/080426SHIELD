/**
 * Hybrid Keycloak OIDC seam (Sprint 9 T6, D-032). Pure, vitest-friendly helpers
 * that keep `options.ts` readable and keep the flag/URL logic testable without a
 * running Auth.js.
 *
 * The seam is FLAG-GATED and default OFF: when `SHIELD_AUTH_OIDC_ENABLED` is not
 * exactly "true" the Keycloak provider is never registered, so ZERO Keycloak
 * discovery / JWKS network requests occur and every credential surface is
 * unchanged (`isOidcEnabled()` is the single gate `options.ts` reads).
 *
 * Split-horizon (Sprint 9 T5): Keycloak advertises ONE canonical issuer
 * (`http://localhost:8080/realms/shield`) to both the browser and the
 * containers, but the backchannel token/JWKS/discovery endpoints must be fetched
 * over the container network (`http://keycloak:8080`). The browser redirect uses
 * the canonical (localhost) authorization endpoint unchanged; only Auth.js's
 * SERVER-side discovery fetch needs the host rewritten to the internal horizon,
 * which is what `keycloakFetch` does. After discovery, Keycloak's
 * backchannel-dynamic config already returns `keycloak:8080` token/JWKS URLs, so
 * the rewrite is a passthrough for every later fetch.
 */

/** The single flag `options.ts` and the sign-in page read. Exact-match "true". */
export function isOidcEnabled(): boolean {
  return process.env.SHIELD_AUTH_OIDC_ENABLED === "true";
}

/**
 * Rewrite the origin of `url` from the public issuer's host to the internal
 * issuer's host, leaving the path + query untouched. Anything that does not
 * start with the public origin (already-internal token/JWKS URLs, or an
 * unrelated host) passes through unchanged.
 *
 * Missing/blank issuer env → passthrough (no rewrite), so a misconfigured deploy
 * fails at discovery with a loud connect error rather than silently sending the
 * browser somewhere unexpected.
 */
export function rewriteKeycloakUrl(
  url: string,
  publicIssuer: string,
  internalIssuer: string,
): string {
  if (!publicIssuer || !internalIssuer) {
    return url;
  }
  let publicOrigin: string;
  let internalOrigin: string;
  try {
    publicOrigin = new URL(publicIssuer).origin;
    internalOrigin = new URL(internalIssuer).origin;
  } catch {
    return url;
  }
  if (url.startsWith(publicOrigin)) {
    return internalOrigin + url.slice(publicOrigin.length);
  }
  return url;
}

/**
 * Auth.js `customFetch` for the Keycloak provider: rewrite only the discovery
 * fetch (the sole URL still on the public/localhost origin server-side) to the
 * container-reachable internal origin, then delegate to the platform `fetch`.
 * Preserves method/headers/body when the input is a `Request`.
 */
export function keycloakFetch(
  input: string | URL | Request,
  init?: RequestInit,
): Promise<Response> {
  const publicIssuer = process.env.KEYCLOAK_ISSUER ?? "";
  const internalIssuer = process.env.KEYCLOAK_INTERNAL_ISSUER ?? "";
  if (input instanceof Request) {
    const rewritten = rewriteKeycloakUrl(
      input.url,
      publicIssuer,
      internalIssuer,
    );
    return rewritten === input.url
      ? fetch(input, init)
      : fetch(new Request(rewritten, input), init);
  }
  const url = typeof input === "string" ? input : input.toString();
  return fetch(rewriteKeycloakUrl(url, publicIssuer, internalIssuer), init);
}
