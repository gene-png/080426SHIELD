import { getToken, type JWT } from "next-auth/jwt";

/**
 * Read-only access to the session cookie, and the rule for when the middleware
 * may write it back (#487).
 *
 * `getToken` DECODES the cookie; it runs no callbacks, so it can neither
 * refresh nor rotate. That is the property both callers need: the middleware
 * compares the token as it arrived with the session after the `jwt` callback
 * ran, and the session-expiry route reports the stored expiry without
 * extending it.
 */

/**
 * next-auth derives secure cookies from the auth URL's protocol, and the
 * dev/CI stack sets `NEXTAUTH_URL` (compose) rather than v5's `AUTH_URL`, which
 * is why `lib/auth/options.ts` reads the secret the same way.
 */
function secureCookiesFor(req: Request): boolean {
  const url = process.env.AUTH_URL ?? process.env.NEXTAUTH_URL ?? req.url;
  return url.startsWith("https:");
}

/** The session cookie's base name. Large sessions are chunked as `<name>.0`, `<name>.1`, … */
export function sessionCookieName(req: Request): string {
  return secureCookiesFor(req)
    ? "__Secure-authjs.session-token"
    : "authjs.session-token";
}

/** The decoded session token as it arrived, or null when there is none or it does not decode. */
export async function readSessionToken(req: Request): Promise<JWT | null> {
  const secret = process.env.AUTH_SECRET ?? process.env.NEXTAUTH_SECRET;
  if (!secret) {
    throw new Error(
      "[auth.session-cookie] no AUTH_SECRET or NEXTAUTH_SECRET -- cannot read the session cookie",
    );
  }
  return getToken({
    req,
    secret,
    secureCookie: secureCookiesFor(req),
    cookieName: sessionCookieName(req),
  });
}

/** What the middleware knows about the session after the `jwt` callback ran. */
export interface SessionAfter {
  accessToken?: string;
  error?: string;
}

/**
 * Whether the session changed in a way the browser must be told about: a new
 * access token (a rotation happened) or a new error (the refresh failed, and the
 * browser must learn it to sign out).
 *
 * Anything else is a re-encoding of the same session, and writing it back is
 * what let a response that was already in flight re-set the cookie after the
 * user had signed out in another tab.
 */
export function sessionChanged(
  before: Pick<JWT, "accessToken" | "error"> | null,
  after: SessionAfter | null,
): boolean {
  return (
    (before?.accessToken ?? null) !== (after?.accessToken ?? null) ||
    (before?.error ?? null) !== (after?.error ?? null)
  );
}

/**
 * Drop every `Set-Cookie` for the session cookie (including its chunks) and
 * keep any other cookie the response sets.
 */
export function stripSessionCookies(headers: Headers, name: string): void {
  const kept = headers.getSetCookie().filter((cookie) => {
    const cookieName = cookie.split("=", 1)[0].trim();
    return cookieName !== name && !cookieName.startsWith(`${name}.`);
  });
  headers.delete("set-cookie");
  for (const cookie of kept) headers.append("set-cookie", cookie);
}
