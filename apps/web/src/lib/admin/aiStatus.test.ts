import { afterEach, describe, expect, it } from "vitest";

import { acknowledgeOffline, hasAcknowledgedOffline } from "./aiStatus";

import type { AiStatus } from "./client";

/**
 * #472: "Continue offline" is a promise that the call stays offline. Both
 * readers of the acknowledgement -- `RunAiGuard` and Tech Debt's
 * auto-extraction on upload -- go through `hasAcknowledgedOffline`, so the rule
 * lives HERE rather than in either caller: a check in the guard alone would
 * leave the upload path running a broken configuration on an old "I know".
 */

function status(over: Partial<AiStatus> = {}): AiStatus {
  return {
    mode: "fixture",
    provider: "anthropic",
    model: "claude-opus-5",
    ready: false,
    detail: "No API key is loaded",
    can_configure: true,
    key_source: "none",
    serves: "offline",
    ...over,
  };
}

afterEach(() => {
  window.sessionStorage.clear();
});

describe("hasAcknowledgedOffline", () => {
  it("honours an acknowledgement of the same offline configuration", () => {
    acknowledgeOffline(status());
    expect(hasAcknowledgedOffline(status())).toBe(true);
  });

  it("never counts for a configuration that will FAIL rather than go offline", () => {
    acknowledgeOffline(status());
    expect(hasAcknowledgedOffline(status({ serves: "broken" }))).toBe(false);
  });

  it("cannot be set for a broken configuration either", () => {
    // Read the STORAGE, not `hasAcknowledgedOffline` -- which refuses a broken
    // status before it looks, so asking it could not tell a write that was
    // refused from one that happened (round 1 on #472).
    acknowledgeOffline(status({ serves: "broken" }));
    expect(window.sessionStorage.length).toBe(0);
  });
});
