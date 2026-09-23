import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The `reauthAt` wiring through the REAL `jwt` and `session` callbacks (#498).
 *
 * `sessionEndsAt` and the API's `reauth_at` are unit-tested on their own, but
 * deleting any one line of the wiring between them -- the seed, the refresh,
 * the session callback -- left every suite green (round 3 of the #487 review).
 * These drive `authConfig.callbacks` directly, which is the surface every
 * session read goes through.
 */

const apiFetch = vi.fn();
vi.mock("@/lib/api", () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
  ApiError: class ApiError extends Error {},
}));
vi.mock("next-auth", () => ({
  default: () => ({
    handlers: {},
    auth: vi.fn(),
    signIn: vi.fn(),
    signOut: vi.fn(),
  }),
  CredentialsSignin: class CredentialsSignin extends Error {},
  customFetch: Symbol("customFetch"),
}));

const { authConfig } = await import("./options");
const { REAUTH_REQUIRED_ERROR } = await import("./errors");

type Cb = (args: Record<string, unknown>) => Promise<Record<string, unknown>>;
const jwt = authConfig.callbacks!.jwt as unknown as Cb;
const session = authConfig.callbacks!.session as unknown as Cb;

const iso = (msFromNow: number) =>
  new Date(Date.now() + msFromNow).toISOString();

beforeEach(() => {
  apiFetch.mockReset();
});

describe("reauthAt through the jwt and session callbacks", () => {
  it("seeds reauthAt from the signed-in user", async () => {
    const reauthAt = iso(24 * 3600_000);
    const token = await jwt({
      token: {},
      user: { role: "admin", accessToken: "a", refreshToken: "r", reauthAt },
    });
    expect(token.reauthAt).toBe(reauthAt);
  });

  it("takes reauth_at from the login response in the credentials authorize", async () => {
    const reauthAt = iso(24 * 3600_000);
    apiFetch
      .mockResolvedValueOnce({
        access_token: "a",
        refresh_token: "r",
        access_expires_at: iso(900_000),
        refresh_expires_at: iso(1800_000),
        reauth_at: reauthAt,
      })
      .mockResolvedValueOnce({
        id: "u1",
        email: "x@example.com",
        role: "admin",
        display_name: null,
      });
    const provider = (
      authConfig.providers as unknown as Array<{
        id: string;
        options?: {
          authorize?: (
            c: Record<string, string>,
          ) => Promise<Record<string, unknown> | null>;
        };
        authorize?: (
          c: Record<string, string>,
        ) => Promise<Record<string, unknown> | null>;
      }>
    ).find((p) => p.id === "credentials");
    const authorize = provider?.options?.authorize ?? provider?.authorize;
    expect(authorize, "credentials provider has no authorize").toBeTypeOf(
      "function",
    );
    const user = await authorize!({ email: "x@example.com", password: "pw" });
    expect(apiFetch).toHaveBeenCalledWith("/auth/login", expect.anything());
    expect(user?.reauthAt).toBe(reauthAt);
  });

  it("carries reauth_at across a refresh", async () => {
    const reauthAt = iso(20 * 3600_000);
    apiFetch.mockResolvedValueOnce({
      access_token: "a2",
      refresh_token: "r2",
      access_expires_at: iso(900_000),
      refresh_expires_at: iso(1800_000),
      reauth_at: reauthAt,
    });
    const token = await jwt({
      token: {
        accessToken: "a1",
        refreshToken: "r1",
        accessExpiresAt: iso(-1000),
      },
    });
    expect(apiFetch).toHaveBeenCalledWith("/auth/refresh", expect.anything());
    expect(token.reauthAt).toBe(reauthAt);
  });

  it("ends the session at the ceiling itself, without asking the backend", async () => {
    // Nothing on the API checks the ceiling until the NEXT refresh, which is up
    // to one access-token lifetime away. Without this the warning counted down
    // to zero, hid itself, and the user was signed out later with no warning.
    const token = await jwt({
      token: {
        accessToken: "a1",
        refreshToken: "r1",
        accessExpiresAt: iso(10 * 60_000), // still valid -- no refresh due
        reauthAt: iso(-1000), // but the ceiling has passed
      },
    });
    expect(token.error).toBe(REAUTH_REQUIRED_ERROR);
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it("ends the session at the EARLIER of refresh expiry and the ceiling", async () => {
    const soon = iso(4 * 60_000);
    const later = iso(25 * 60_000);
    const out = await session({
      session: {},
      token: { refreshExpiresAt: later, reauthAt: soon },
    });
    expect(out.sessionExpiresAt).toBe(soon);
  });
});
