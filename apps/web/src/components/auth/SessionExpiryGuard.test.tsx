import "@testing-library/jest-dom/vitest";

import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OIDC_EXCHANGE_ERROR, REAUTH_REQUIRED_ERROR } from "@/lib/auth/errors";

import { SessionExpiryGuard } from "./SessionExpiryGuard";

// Drive the guard by controlling the session error and asserting the signOut
// callbackUrl. Both next-auth client hooks are mocked so the test is offline.
const useSessionMock = vi.fn();
const signOutMock = vi.fn();
vi.mock("next-auth/react", () => ({
  useSession: () => useSessionMock(),
  signOut: (...args: unknown[]) => signOutMock(...args),
}));

describe("SessionExpiryGuard", () => {
  beforeEach(() => {
    useSessionMock.mockReset();
    signOutMock.mockReset();
  });

  it("does nothing when the session carries no error", () => {
    useSessionMock.mockReturnValue({ data: { error: undefined } });
    render(<SessionExpiryGuard />);
    expect(signOutMock).not.toHaveBeenCalled();
  });

  it("signs out to session_expired on the reauth signal", async () => {
    useSessionMock.mockReturnValue({ data: { error: REAUTH_REQUIRED_ERROR } });
    render(<SessionExpiryGuard />);
    await waitFor(() =>
      expect(signOutMock).toHaveBeenCalledWith({
        callbackUrl: "/sign-in?reason=session_expired",
      }),
    );
  });

  it("signs out to oidc_exchange_failed on the OIDC exchange signal", async () => {
    useSessionMock.mockReturnValue({ data: { error: OIDC_EXCHANGE_ERROR } });
    render(<SessionExpiryGuard />);
    await waitFor(() =>
      expect(signOutMock).toHaveBeenCalledWith({
        callbackUrl: "/sign-in?reason=oidc_exchange_failed",
      }),
    );
  });
});
