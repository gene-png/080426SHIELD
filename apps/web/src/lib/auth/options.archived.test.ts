import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * #727, D-104: `POST /auth/refresh` refuses a user of an archived client with a
 * typed 403, reason `client_archived`. That refusal is final, so the jwt
 * callback must end the session through REAUTH_REQUIRED_ERROR (which the guard
 * signs out on) rather than the generic error the guard ignores.
 */

class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly correlationId: string | undefined,
    public readonly payload: unknown,
  ) {
    super(`API ${status}`);
  }
}

const apiFetch = vi.fn();
vi.mock("@/lib/api", () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
  ApiError,
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

const iso = (msFromNow: number) =>
  new Date(Date.now() + msFromNow).toISOString();

function refreshDue() {
  return {
    token: {
      accessToken: "a1",
      refreshToken: "r1",
      accessExpiresAt: iso(-1000),
      refreshExpiresAt: iso(3600_000),
      reauthAt: iso(3600_000),
    },
  };
}

beforeEach(() => {
  apiFetch.mockReset();
});

describe("refresh refused because the client is archived", () => {
  it("ends the session through the reauth signal", async () => {
    apiFetch.mockRejectedValueOnce(
      new ApiError(403, undefined, {
        error: { reason: "client_archived", message: "archived" },
      }),
    );

    const token = await jwt(refreshDue());

    expect(apiFetch).toHaveBeenCalledWith("/auth/refresh", expect.anything());
    expect(token.error).toBe(REAUTH_REQUIRED_ERROR);
  });

  it("still treats an unrecognised refusal as the generic error", async () => {
    apiFetch.mockRejectedValueOnce(
      new ApiError(403, undefined, {
        error: { reason: "something_else", message: "no" },
      }),
    );

    const token = await jwt(refreshDue());

    expect(token.error).toBe("RefreshAccessTokenError");
  });
});
