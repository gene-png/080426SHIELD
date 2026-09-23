import { describe, expect, it } from "vitest";

import { sessionChanged, stripSessionCookies } from "./session-cookie";

/**
 * #487's review: the middleware wrote the session cookie on EVERY response, so a
 * response that was already in flight could re-set it after the user signed out
 * in another tab. The rule below limits writes to real changes.
 */
describe("sessionChanged", () => {
  it("is false for the same session re-encoded", () => {
    expect(sessionChanged({ accessToken: "a1" }, { accessToken: "a1" })).toBe(
      false,
    );
  });

  it("is true when a rotation produced a new access token", () => {
    expect(sessionChanged({ accessToken: "a1" }, { accessToken: "a2" })).toBe(
      true,
    );
  });

  it("is true when a refresh failed, so the browser learns it must sign out", () => {
    // The session callback hides the access token once an error is set.
    expect(
      sessionChanged(
        { accessToken: "a1" },
        { accessToken: undefined, error: "reauth_required" },
      ),
    ).toBe(true);
  });

  it("is false with no session before or after (an anonymous page)", () => {
    expect(sessionChanged(null, null)).toBe(false);
  });
});

describe("stripSessionCookies", () => {
  it("drops the session cookie and its chunks and keeps every other cookie", () => {
    const headers = new Headers();
    headers.append("set-cookie", "authjs.session-token=abc; Path=/; HttpOnly");
    headers.append("set-cookie", "authjs.session-token.0=p0; Path=/");
    headers.append("set-cookie", "authjs.session-token.1=p1; Path=/");
    headers.append("set-cookie", "shield_active_client=c1; Path=/");
    stripSessionCookies(headers, "authjs.session-token");
    expect(headers.getSetCookie()).toEqual(["shield_active_client=c1; Path=/"]);
  });

  it("does not drop a cookie that merely starts with the same letters", () => {
    const headers = new Headers();
    headers.append("set-cookie", "authjs.session-token-other=x; Path=/");
    stripSessionCookies(headers, "authjs.session-token");
    expect(headers.getSetCookie()).toEqual([
      "authjs.session-token-other=x; Path=/",
    ]);
  });
});
