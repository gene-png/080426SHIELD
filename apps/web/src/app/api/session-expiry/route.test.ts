import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * `/api/session-expiry` reports when the session ENDS: the earlier of the
 * rolling refresh expiry and the fixed re-auth ceiling (#498). Only the cookie
 * read is mocked; `sessionEndsAt` is the real rule.
 */

const readSessionToken = vi.fn();
vi.mock("@/lib/auth/session-cookie", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/auth/session-cookie")>()),
  readSessionToken: (...args: unknown[]) => readSessionToken(...args),
}));

const { GET } = await import("./route");

beforeEach(() => {
  readSessionToken.mockReset();
});

describe("GET /api/session-expiry", () => {
  it("reports the re-auth ceiling when it comes before the refresh expiry", async () => {
    readSessionToken.mockResolvedValueOnce({
      refreshExpiresAt: "2026-09-24T09:00:00.000Z",
      reauthAt: "2026-09-23T12:00:00.000Z",
    });
    const body = await (
      await GET(new Request("http://localhost/api/session-expiry"))
    ).json();
    expect(body.sessionExpiresAt).toBe("2026-09-23T12:00:00.000Z");
  });

  it("reports null when there is no session", async () => {
    readSessionToken.mockResolvedValueOnce(null);
    const body = await (
      await GET(new Request("http://localhost/api/session-expiry"))
    ).json();
    expect(body.sessionExpiresAt).toBeNull();
    // No cookie means no session: it HAS ended, and the warning signs the
    // tab out rather than waiting for an end that already happened.
    expect(body.ended).toBe(true);
  });

  it("refuses LOUDLY when a session cookie is present but will not decode", async () => {
    // A secret or cookie-name mismatch would otherwise read a LIVE session as
    // `ended` and sign the user out (round 7 on #499). A failed read is not an
    // answer, so the warning does nothing on it.
    readSessionToken.mockResolvedValueOnce(null);
    const error = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    const res = await GET(
      new Request("http://localhost/api/session-expiry", {
        headers: { cookie: "authjs.session-token.0=abc; other=1" },
      }),
    );
    expect(res.status).toBe(500);
    const body = await res.json();
    expect(body.reason).toBe("session_cookie_unreadable");
    expect(body).not.toHaveProperty("ended");
    expect(error).toHaveBeenCalled();
    error.mockRestore();
  });

  // `ended` is decided on THIS server's clock, the one the jwt callback uses,
  // so the warning never has to trust the browser's (round 5 on #499).
  it("says the session has ended once its end has passed on the server clock", async () => {
    readSessionToken.mockResolvedValueOnce({
      refreshExpiresAt: new Date(Date.now() - 1_000).toISOString(),
    });
    const body = await (
      await GET(new Request("http://localhost/api/session-expiry"))
    ).json();
    expect(body.ended).toBe(true);
  });

  it("says the session has NOT ended while its end is still ahead", async () => {
    readSessionToken.mockResolvedValueOnce({
      refreshExpiresAt: new Date(Date.now() + 60_000).toISOString(),
    });
    const body = await (
      await GET(new Request("http://localhost/api/session-expiry"))
    ).json();
    expect(body.ended).toBe(false);
  });
});
