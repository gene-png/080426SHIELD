/**
 * Both halves of the AI-mode gate, because a guard watched only firing is
 * half-tested.
 *
 * `CLAUDE.md`: "a guard must be observed in BOTH states before it is trusted.
 * Watching it fire proves it fires; it does not prove it passes. A typo that
 * halts unconditionally leaves every agent dead on arrival, and that symptom
 * is indistinguishable from the hazard the guard exists to catch."
 *
 * Here that matters more than usual: a gate that refused unconditionally would
 * block every rehearsal, and a gate that passed unconditionally would let
 * failed-item 2.2 through — a whole take recorded in fixture believing it is
 * live. So each of the four intent/actual combinations is pinned.
 *
 * **The live-actual cases are STUBBED, and that is the honest limit.** Making
 * the running stack report live means pasting an API key, which Phase 1
 * forbids. These prove the DECISION is right given a live status; they prove
 * nothing about whether the real endpoint reports live correctly when a key is
 * present. That half is unexercised and is recorded as such in
 * `kentro-demo-failed-items.md` 2.2.
 *
 * No browser is launched: `test` is used for its runner, and nothing here
 * destructures a page fixture.
 */
import { expect, test } from "@playwright/test";

import {
  AiModeRefusal,
  actualAiMode,
  assertAiModeMatches,
  intendedAiMode,
} from "./aiModeGate";

/** A realistic fixture-mode payload, matching `AdminAiStatus`'s shape. */
const FIXTURE_STATUS = {
  ready: false,
  mode: "fixture",
  provider: "anthropic",
  model: "claude-opus-5",
  key_source: "none",
  detail:
    "No API key is loaded — AI steps will generate offline (fixture) responses.",
};

/**
 * A live payload. Note `mode: "fixture"` beside `ready: true` — that is NOT a
 * contrived combination, it is the exact state a key pasted through Admin ->
 * Management produces: `_ai_readiness` short-circuits its mode check when
 * `source == "database"`, so the stack runs live while SHIELD_LLM_MODE still
 * reads fixture. A gate keyed on `mode` would call this fixture and wave
 * through the very thing it exists to catch.
 */
const LIVE_STATUS_VIA_DB_KEY = {
  ready: true,
  mode: "fixture",
  provider: "anthropic",
  model: "claude-opus-5",
  key_source: "database",
  detail: "Live AI configured (anthropic/claude-opus-5).",
};

test.describe("AI mode gate", () => {
  test("passes when a rehearsal intends fixture and the stack is fixture", () => {
    expect(() => assertAiModeMatches("fixture", FIXTURE_STATUS)).not.toThrow();
  });

  test("passes when a take intends live and the stack is live", () => {
    expect(() =>
      assertAiModeMatches("live", LIVE_STATUS_VIA_DB_KEY),
    ).not.toThrow();
  });

  test("REFUSES a take that intends live against a fixture stack (item 2.2)", () => {
    // The case the gate exists for: the key was wiped and nothing said so.
    expect(() => assertAiModeMatches("live", FIXTURE_STATUS)).toThrow(
      AiModeRefusal,
    );
    // The message must name both sides, or it cannot be acted on.
    expect(() => assertAiModeMatches("live", FIXTURE_STATUS)).toThrow(
      /intended: live[\s\S]*actual:\s+fixture/,
    );
  });

  test("REFUSES a rehearsal that intends fixture against a live stack", () => {
    // The Phase 1 boundary, made mechanical: this run would spend real tokens.
    expect(() =>
      assertAiModeMatches("fixture", LIVE_STATUS_VIA_DB_KEY),
    ).toThrow(AiModeRefusal);
  });

  test("keys on `ready`, not on `mode`", () => {
    // The whole point, pinned directly: a payload whose `mode` says fixture
    // and whose `ready` says true is LIVE. If this ever reads "fixture" the
    // gate has started trusting the env var and 2.2 is reopened.
    expect(actualAiMode(LIVE_STATUS_VIA_DB_KEY)).toBe("live");
    expect(LIVE_STATUS_VIA_DB_KEY.mode).toBe("fixture");
  });

  test("refuses an unreadable status rather than calling it fixture", () => {
    // "I could not look" must not share a branch with "nothing to complain
    // about" — this repo's most-repeated gate defect. A missing `ready` is
    // NOT a fixture stack.
    expect(() => actualAiMode({})).toThrow(AiModeRefusal);
    expect(() => actualAiMode({ ready: "yes" })).toThrow(AiModeRefusal);
    expect(() => actualAiMode({ mode: "fixture" })).toThrow(AiModeRefusal);
    expect(() =>
      actualAiMode(null as unknown as Record<string, unknown>),
    ).toThrow(AiModeRefusal);
  });

  test("defaults the intent to fixture and refuses an unrecognised one", () => {
    expect(intendedAiMode({} as NodeJS.ProcessEnv)).toBe("fixture");
    expect(
      intendedAiMode({
        SHIELD_ENGAGEMENT_AI_MODE: "LIVE",
      } as NodeJS.ProcessEnv),
    ).toBe("live");
    // A typo must not silently fall back to the default: "I could not read the
    // intent" and "the intent is fixture" are different claims.
    expect(() =>
      intendedAiMode({
        SHIELD_ENGAGEMENT_AI_MODE: "liev",
      } as NodeJS.ProcessEnv),
    ).toThrow(AiModeRefusal);
  });
});
