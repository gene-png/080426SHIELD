import "@testing-library/jest-dom/vitest";

import { render, waitFor } from "@testing-library/react";
import * as React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SessionExpiryGuard } from "./SessionExpiryGuard";

// #658/#670: a password reset makes the API refuse the old access token with a
// typed 401, reason `credentials_changed`, on EVERY request -- and ~20 files
// call `fetch("/api/proxy/...")` directly, besides the six service clients. So
// the guard watches `fetch` once, globally, and signs out through the same
// session_expired path as the refresh-refusal signal. These tests pin that it
// only observes: one sign-out, only for that 401 on a proxy URL, the original
// response untouched, and fetch restored on unmount.

const useSessionMock = vi.fn();
const signOutMock = vi.fn();
vi.mock("next-auth/react", () => ({
  useSession: () => useSessionMock(),
  signOut: (...args: unknown[]) => signOutMock(...args),
}));

const SESSION_EXPIRED = { callbackUrl: "/sign-in?reason=session_expired" };

function envelope(reason: string): string {
  return JSON.stringify({
    error: { code: 401, reason, message: "Sign in again." },
  });
}

let underlying: ReturnType<typeof vi.fn>;
let original: typeof window.fetch;

function respondWith(status: number, body: string): void {
  underlying.mockImplementation(async () => new Response(body, { status }));
}

beforeEach(() => {
  useSessionMock.mockReset();
  signOutMock.mockReset();
  useSessionMock.mockReturnValue({ data: { error: undefined } });
  original = window.fetch;
  underlying = vi.fn();
  window.fetch = underlying as unknown as typeof window.fetch;
});

afterEach(() => {
  window.fetch = original;
});

async function settle(): Promise<void> {
  // The watch reads a CLONE asynchronously, after returning the response.
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
}

describe("SessionExpiryGuard watching fetch for credentials_changed", () => {
  it("signs out once, to session_expired, on a credentials_changed 401 from a proxy URL", async () => {
    render(<SessionExpiryGuard />);
    respondWith(401, envelope("credentials_changed"));

    await Promise.all([
      window.fetch("/api/proxy/tech-debt/services/1"),
      window.fetch("/api/proxy/csf/services/2"),
      window.fetch("/api/proxy/zt/services/3"),
    ]);

    await waitFor(() =>
      expect(signOutMock).toHaveBeenCalledWith(SESSION_EXPIRED),
    );
    await settle();
    expect(signOutMock).toHaveBeenCalledTimes(1);
  });

  it.each([
    [
      "another 401 reason",
      "/api/proxy/csf/services/1",
      401,
      envelope("refresh_reused"),
    ],
    [
      "a 500 carrying the same reason",
      "/api/proxy/csf/services/1",
      500,
      envelope("credentials_changed"),
    ],
    [
      "a non-proxy URL",
      "/api/auth/session",
      401,
      envelope("credentials_changed"),
    ],
    [
      "a cross-origin URL with a proxy path",
      "https://elsewhere.example/api/proxy/x",
      401,
      envelope("credentials_changed"),
    ],
    [
      "a body that does not parse",
      "/api/proxy/csf/services/1",
      401,
      "not json {",
    ],
    [
      "a body with no error envelope",
      "/api/proxy/csf/services/1",
      401,
      JSON.stringify({ detail: "x" }),
    ],
  ])("does nothing for %s", async (_label, url, status, body) => {
    // "Does nothing" includes not failing somewhere the caller cannot see: the
    // watch reads the clone in a detached promise, so a throw there surfaces
    // only as an unhandled rejection, never as this test's own failure.
    const unhandled: unknown[] = [];
    const onUnhandled = (reason: unknown) => unhandled.push(reason);
    process.on("unhandledRejection", onUnhandled);
    try {
      render(<SessionExpiryGuard />);
      respondWith(status, body);

      const response = await window.fetch(url);

      expect(response.status).toBe(status);
      await settle();
      expect(signOutMock).not.toHaveBeenCalled();
      expect(unhandled).toEqual([]);
    } finally {
      process.off("unhandledRejection", onUnhandled);
    }
  });

  it("returns the original response, still readable by the caller", async () => {
    render(<SessionExpiryGuard />);
    const body = envelope("credentials_changed");
    respondWith(401, body);

    const response = await window.fetch("/api/proxy/csf/services/1");

    expect(await response.text()).toBe(body);
  });

  it("wraps fetch once however many times it mounts", async () => {
    render(
      <React.StrictMode>
        <SessionExpiryGuard />
        <SessionExpiryGuard />
      </React.StrictMode>,
    );
    respondWith(401, envelope("credentials_changed"));

    await window.fetch("/api/proxy/csf/services/1");

    expect(underlying).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(signOutMock).toHaveBeenCalledTimes(1));
  });

  it("restores the original fetch on unmount", () => {
    const before = window.fetch;
    const { unmount } = render(<SessionExpiryGuard />);
    expect(window.fetch).not.toBe(before);

    unmount();

    expect(window.fetch).toBe(before);
  });
});
