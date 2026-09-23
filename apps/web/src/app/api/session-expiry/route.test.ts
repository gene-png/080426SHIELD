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
    expect(body.ended).toBe(false);
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
