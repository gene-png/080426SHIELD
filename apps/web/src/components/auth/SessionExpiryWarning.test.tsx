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
const update = vi.fn(async () => null);
let sessionData: { sessionExpiresAt?: string } | null = null;

vi.mock("next-auth/react", () => ({
  useSession: () => ({ data: sessionData, update }),
  signOut: (...args: unknown[]) => signOut(...args),
}));

/** A session that ends `ms` from now. */
function expiringIn(ms: number): void {
  sessionData = { sessionExpiresAt: new Date(Date.now() + ms).toISOString() };
}

/** What `/api/session-expiry` answers; null means "no stored expiry". */
let storedExpiry: string | null = null;
const fetchMock = vi.fn(async (url: string) => {
  if (url !== "/api/session-expiry") throw new Error(`unexpected fetch ${url}`);
  return new Response(JSON.stringify({ sessionExpiresAt: storedExpiry }), {
    status: 200,
  });
});

beforeEach(() => {
  vi.useFakeTimers();
  signOut.mockReset();
  update.mockClear();
  sessionData = null;
  storedExpiry = null;
  fetchMock.mockClear();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

/** Let the component's pending `/api/session-expiry` read settle. */
async function settle(): Promise<void> {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

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

  it("at the deadline, asks the server ONCE whether the session ended", async () => {
    // The guard only sees useSession, which refetches on focus. Without this a
    // user who never left the page watched the countdown vanish and typed into
    // 401s. update() runs the jwt callback, which ends the session; the guard
    // then signs out with the reason. The banner itself stays quiet.
    expiringIn(-1_000);
    render(<SessionExpiryWarning />);
    await settle();
    expect(screen.queryByTestId("session-expiry-warning")).toBeNull();
    expect(update).toHaveBeenCalledTimes(1);
    await act(async () => {
      vi.advanceTimersByTime(5_000);
    });
    expect(update).toHaveBeenCalledTimes(1);
  });

  it("does not ask the server while time remains", async () => {
    expiringIn(30 * 60_000);
    render(<SessionExpiryWarning />);
    await settle();
    expect(update).not.toHaveBeenCalled();
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

  // #498: the cached expiry is the one from sign-in; since #487 persists
  // rotations, the COOKIE's expiry rolls forward and the cache does not.
  it("trusts the stored expiry over a stale cached one, so a live session is not warned", async () => {
    expiringIn(4 * 60_000); // the stale cache says four minutes left
    storedExpiry = new Date(Date.now() + 25 * 60_000).toISOString();
    render(<SessionExpiryWarning />);
    await settle();
    expect(fetchMock).toHaveBeenCalledWith("/api/session-expiry", {
      cache: "no-store",
    });
    expect(screen.queryByTestId("session-expiry-warning")).toBeNull();
  });

  it("still warns when the stored expiry really is close", async () => {
    expiringIn(25 * 60_000);
    storedExpiry = new Date(Date.now() + 4 * 60_000).toISOString();
    render(<SessionExpiryWarning />);
    await settle();
    expect(screen.getByTestId("session-expiry-warning")).toBeInTheDocument();
  });

  it("falls back to the cached expiry when the stored one cannot be read", async () => {
    fetchMock.mockImplementationOnce(
      async () => new Response("", { status: 500 }),
    );
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    expiringIn(4 * 60_000);
    render(<SessionExpiryWarning />);
    await settle();
    expect(screen.getByTestId("session-expiry-warning")).toBeInTheDocument();
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });

  it("re-reads the stored expiry each minute and never calls /api/auth/session", async () => {
    // Polling /api/auth/session would refresh and extend the session, so an
    // idle tab would never time out. Only the decode-only route is polled.
    expiringIn(60 * 60_000);
    render(<SessionExpiryWarning />);
    await settle();
    await act(async () => {
      vi.advanceTimersByTime(3 * 60_000);
    });
    await settle();
    const urls = fetchMock.mock.calls.map((c) => c[0]);
    expect(urls.length).toBeGreaterThanOrEqual(4);
    expect(new Set(urls)).toEqual(new Set(["/api/session-expiry"]));
  });
});
