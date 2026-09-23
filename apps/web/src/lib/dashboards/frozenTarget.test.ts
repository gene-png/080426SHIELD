/**
 * #209: the sentence disclosing that a dashboard's figures were computed against
 * a LIVE target rather than the one its released report was rendered against.
 *
 * Two states and both are pinned, because the SILENT one is a claim. Returning
 * "" for a frozen dashboard says "these figures agree with your report"; if that
 * arm ever started returning text, every dashboard in the product would carry a
 * disclosure about the normal case and readers would learn to skip the line --
 * which is how the one case that matters becomes invisible.
 */

import { describe, expect, it } from "vitest";

import { renderedAgainstNote } from "./frozenTarget";

describe("renderedAgainstNote", () => {
  it("says the figures are live when nothing was frozen", () => {
    expect(renderedAgainstNote(null)).toBe(
      " These figures use your target as it stands today. Your released report" +
        " was rendered against the target on file at the time, so the two can" +
        " differ.",
    );
  });

  it("says NOTHING when the target was frozen", () => {
    expect(renderedAgainstNote("2026-09-06T00:00:00Z")).toBe("");
  });

  it("names no control the reader does not have", () => {
    // `CLAUDE.md`: a user-facing string naming an action must name a control
    // that exists and works today. A client cannot re-freeze a report from a
    // dashboard, so this sentence states the fact and stops.
    const note = renderedAgainstNote(null);
    for (const imperative of [
      "contact",
      "click",
      "update your",
      "set your",
      "re-run",
      "ask your",
    ]) {
      expect(note.toLowerCase()).not.toContain(imperative);
    }
  });
});
