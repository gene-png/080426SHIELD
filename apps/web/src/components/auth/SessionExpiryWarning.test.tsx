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

// Resolves like the real one; `signOut` returns a Promise.
const signOut = vi.fn(async (..._args: unknown[]) => undefined);
let sessionData: { sessionExpiresAt?: string } | null = null;

vi.mock("next-auth/react", () => ({
  useSession: () => ({ data: sessionData }),
  signOut: (...args: unknown[]) => signOut(...args),
}));

/** A session that ends `ms` from now. */
function expiringIn(ms: number): void {
  sessionData = { sessionExpiresAt: new Date(Date.now() + ms).toISOString() };
}

/** What `/api/session-expiry` answers; null means "no stored expiry". */
let storedExpiry: string | null = null;
/** Whether the SERVER's clock says the session has ended. */
let serverSaysEnded = false;
async function answer(url: string): Promise<Response> {
  if (url !== "/api/session-expiry") throw new Error(`unexpected fetch ${url}`);
  return new Response(
    JSON.stringify({ sessionExpiresAt: storedExpiry, ended: serverSaysEnded }),
    { status: 200 },
  );
}
const fetchMock = vi.fn(answer);

beforeEach(() => {
  vi.useFakeTimers();
  signOut.mockReset();
  signOut.mockImplementation(async () => undefined);
  sessionData = null;
  storedExpiry = null;
  serverSaysEnded = false;
  fetchMock.mockReset();
  fetchMock.mockImplementation(answer);
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

  // SPECIFICATION CHANGE, round 7 on #499. Rounds 4-6 answered `ended` with
  // update(), trusting the jwt callback and the guard to sign out. But
  // update() resolves `undefined` while another fetch is in flight and `null`
  // both for "no session" and for a failed fetch, and next-auth drops a null
  // -- so a tab whose cookie was gone looped on it for good with no sign-out.
  // `ended` IS the server's answer, on the callback's own clock, so the
  // warning now signs out directly, with the reason the guard would give.
  it("once the SERVER says the session ended, signs out with the reason -- once", async () => {
    expiringIn(-1_000);
    storedExpiry = sessionData!.sessionExpiresAt!;
    serverSaysEnded = true;
    render(<SessionExpiryWarning />);
    await settle();
    expect(screen.queryByTestId("session-expiry-warning")).toBeNull();
    expect(signOut).toHaveBeenCalledTimes(1);
    expect(signOut).toHaveBeenCalledWith({
      callbackUrl: "/sign-in?reason=session_expired",
    });
    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });
    await settle();
    expect(signOut).toHaveBeenCalledTimes(1);
  });

  it("does NOT act on the browser's clock alone -- a browser ahead of the server must not end or extend a live session", async () => {
    // Round 5: update() here ran the jwt callback, which REFRESHES a session
    // the server still considers alive. Signing out would be the opposite
    // error. Either way, the browser's clock is not the server's.
    expiringIn(-1_000);
    storedExpiry = sessionData!.sessionExpiresAt!;
    serverSaysEnded = false;
    render(<SessionExpiryWarning />);
    await settle();
    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });
    await settle();
    expect(signOut).not.toHaveBeenCalled();
  });

  it("past its own deadline, re-asks the server soon rather than in a minute", async () => {
    expiringIn(-1_000);
    storedExpiry = sessionData!.sessionExpiresAt!;
    render(<SessionExpiryWarning />);
    await settle();
    const before = fetchMock.mock.calls.length;
    serverSaysEnded = true;
    await act(async () => {
      vi.advanceTimersByTime(10_000);
    });
    await settle();
    expect(fetchMock.mock.calls.length).toBeGreaterThan(before);
    expect(signOut).toHaveBeenCalledTimes(1);
  });

  it("acts on the server's `ended` even while the BROWSER's clock says time remains", async () => {
    // A browser clock behind the server's: the server has ended the session,
    // every proxy call is a 401, and the banner must not count down minutes
    // the user does not have (round 6 on #499).
    expiringIn(3 * 60_000);
    storedExpiry = sessionData!.sessionExpiresAt!;
    serverSaysEnded = true;
    render(<SessionExpiryWarning />);
    await settle();
    expect(signOut).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId("session-expiry-warning")).toBeNull();
  });

  it("tries the sign-out again when it fails", async () => {
    // A sign-out that failed on a network blip must not leave the tab on a
    // dead session for good.
    expiringIn(-1_000);
    storedExpiry = sessionData!.sessionExpiresAt!;
    serverSaysEnded = true;
    signOut.mockImplementationOnce(async () => {
      throw new Error("network blip");
    });
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    render(<SessionExpiryWarning />);
    await settle();
    expect(signOut).toHaveBeenCalledTimes(1);
    await act(async () => {
      vi.advanceTimersByTime(6_000);
    });
    await settle();
    expect(signOut).toHaveBeenCalledTimes(2);
    warn.mockRestore();
  });

  it("can still sign out after a failed attempt was interrupted by the session reviving", async () => {
    // A failed sign-out waits five seconds to retry. If `ended` flips false in
    // that window, the pending retry is cancelled -- and must not leave the
    // page believing a sign-out is still under way (round 8 on #499).
    //
    // The timing is exact on purpose: the deadline is reached at 58 s (the
    // re-check reads `ended` and the sign-out fails), the minute poll at 60 s
    // reads the session alive INSIDE the 5 s retry window, and the re-check
    // at 65 s reads it ended again. A looser schedule lets the retry fire
    // first, and the test then passes against the defect it is named for.
    expiringIn(58_000);
    storedExpiry = sessionData!.sessionExpiresAt!;
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    render(<SessionExpiryWarning />);
    await settle();

    serverSaysEnded = true;
    signOut.mockImplementationOnce(async () => {
      throw new Error("network blip");
    });
    await act(async () => {
      vi.advanceTimersByTime(58_000);
    });
    await settle();
    await settle();
    expect(signOut).toHaveBeenCalledTimes(1);

    serverSaysEnded = false;
    await act(async () => {
      vi.advanceTimersByTime(2_000); // t=60: the poll reads it alive
    });
    await settle();
    await settle();

    serverSaysEnded = true;
    await act(async () => {
      vi.advanceTimersByTime(6_000); // t=65: the re-check reads it ended
    });
    await settle();
    await settle();
    expect(signOut).toHaveBeenCalledTimes(2);
    warn.mockRestore();
  });

  it("does not start a second sign-out while one is still in flight", async () => {
    // What `signingOut` is for. The first sign-out never settles; `ended`
    // flips false at the 60 s poll and true again at the 65 s re-check, which
    // re-runs the effect. Without the flag that starts a second, concurrent
    // sign-out. Same exact schedule as the reviving test above.
    expiringIn(58_000);
    storedExpiry = sessionData!.sessionExpiresAt!;
    render(<SessionExpiryWarning />);
    await settle();

    serverSaysEnded = true;
    signOut.mockImplementationOnce(() => new Promise<undefined>(() => {}));
    await act(async () => {
      vi.advanceTimersByTime(58_000);
    });
    await settle();
    await settle();
    expect(signOut).toHaveBeenCalledTimes(1);

    serverSaysEnded = false;
    await act(async () => {
      vi.advanceTimersByTime(2_000);
    });
    await settle();
    await settle();
    serverSaysEnded = true;
    await act(async () => {
      vi.advanceTimersByTime(6_000);
    });
    await settle();
    await settle();
    expect(signOut).toHaveBeenCalledTimes(1);
  });

  it("does not sign out when the server cannot be asked", async () => {
    // A failed read is not an answer: the cached expiry may be stale, and
    // update() on a live session would extend it.
    fetchMock.mockImplementation(async () => new Response("", { status: 500 }));
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    expiringIn(-1_000);
    render(<SessionExpiryWarning />);
    await settle();
    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });
    await settle();
    expect(signOut).not.toHaveBeenCalled();
    warn.mockRestore();
  });

  it("does not sign out while time remains, whatever the stored expiry says", async () => {
    // Was "does not ask the server while time remains", asserting only on
    // update() -- which the component no longer calls, so it could not fail
    // (round 9 on #499). What must not happen while time remains is a
    // sign-out, and only the decode-only route may be read.
    expiringIn(30 * 60_000);
    storedExpiry = sessionData!.sessionExpiresAt!;
    render(<SessionExpiryWarning />);
    await settle();
    expect(signOut).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledWith("/api/session-expiry", {
      cache: "no-store",
    });
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
