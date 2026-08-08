import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SessionExpiryWarning } from "./SessionExpiryWarning";

/**
 * Sessions used to end with no warning at all. The rotation race that caused
 * most of those is fixed, but a session still has a real ceiling, and walking
 * into it mid-assessment is its own defect — the client self-assessment is 37
 * questions long.
 */

const signOut = vi.fn();
let sessionData: { sessionExpiresAt?: string } | null = null;

vi.mock("next-auth/react", () => ({
  useSession: () => ({ data: sessionData }),
  signOut: (...args: unknown[]) => signOut(...args),
}));

/** A session that ends `ms` from now. */
function expiringIn(ms: number): void {
  sessionData = { sessionExpiresAt: new Date(Date.now() + ms).toISOString() };
}

beforeEach(() => {
  vi.useFakeTimers();
  signOut.mockReset();
  sessionData = null;
});

afterEach(() => {
  vi.useRealTimers();
});

describe("SessionExpiryWarning", () => {
  it("says nothing while the session is comfortably alive", () => {
    expiringIn(60 * 60_000);
    render(<SessionExpiryWarning />);
    expect(screen.queryByTestId("session-expiry-warning")).toBeNull();
  });

  it("warns at the five-minute mark", () => {
    expiringIn(4 * 60_000 + 30_000);
    render(<SessionExpiryWarning />);
    expect(screen.getByTestId("session-expiry-warning")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      /signed out in about 5 minutes/i,
    );
  });

  it("escalates at the one-minute mark", () => {
    expiringIn(45_000);
    render(<SessionExpiryWarning />);
    expect(screen.getByRole("alert")).toHaveTextContent(
      /signed out in less than a minute/i,
    );
  });

  it("crosses from the five-minute warning into the one-minute one as time passes", () => {
    expiringIn(5 * 60_000 + 2_000);
    render(<SessionExpiryWarning />);
    expect(screen.queryByTestId("session-expiry-warning")).toBeNull();

    act(() => void vi.advanceTimersByTime(30_000));
    expect(screen.getByRole("alert")).toHaveTextContent(/about 5 minutes/i);

    act(() => void vi.advanceTimersByTime(4 * 60_000 + 30_000));
    expect(screen.getByRole("alert")).toHaveTextContent(/less than a minute/i);
  });

  it("dismissing the five-minute notice does not suppress the one-minute one", () => {
    // The whole point: "I'll deal with it later" must stop being accepted once
    // later has arrived.
    expiringIn(4 * 60_000);
    render(<SessionExpiryWarning />);
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByTestId("session-expiry-warning")).toBeNull();

    act(() => void vi.advanceTimersByTime(3 * 60_000 + 30_000));
    expect(screen.getByRole("alert")).toHaveTextContent(/less than a minute/i);
  });

  it("stays quiet when the session carries no expiry", () => {
    sessionData = {};
    render(<SessionExpiryWarning />);
    expect(screen.queryByTestId("session-expiry-warning")).toBeNull();
  });

  it("stays quiet once the deadline has passed — the guard owns the sign-out", () => {
    expiringIn(-1_000);
    render(<SessionExpiryWarning />);
    expect(screen.queryByTestId("session-expiry-warning")).toBeNull();
  });

  it("offers a way to re-authenticate without losing the reason", () => {
    expiringIn(30_000);
    render(<SessionExpiryWarning />);
    fireEvent.click(screen.getByRole("button", { name: "Sign in again" }));
    expect(signOut).toHaveBeenCalledWith({
      callbackUrl: "/sign-in?reason=session_expired",
    });
  });

  it("announces assertively — a timed warning must not wait to be discovered", () => {
    expiringIn(30_000);
    render(<SessionExpiryWarning />);
    expect(screen.getByRole("alert")).toHaveAttribute("aria-live", "assertive");
  });
});
