import { describe, expect, it } from "vitest";

import {
  BELOW_FLOOR_SOURCE,
  STAGE_BELOW_FLOOR_NOTE,
  TARGET_SOURCE_NOTES,
  TIER_BELOW_FLOOR_NOTE,
} from "@/lib/assessment-targets";

import { targetFaultNote } from "./csf";
import { targetFault } from "./zt";

/**
 * #783 / #422: the client's dashboard and the client's documents describe a
 * default target in the same words, because both read ONE table,
 * `TARGET_SOURCE_NOTES` in `lib/assessment-targets.ts`.
 *
 * What this file pins is the DERIVATION: that the dashboards read that table,
 * row for row, and nothing else. The WORDS are pinned on the api side, where
 * `test_target_floor_parity.py` asserts the api's copy equal to this table and
 * `test_target_source_in_deliverables.py` asserts every row in the stored
 * PDF, DOCX, XLSX and `/results` summary, both reading this file through the
 * api container's read-only mount.
 */
describe("the dashboards' default-target notes derive from the one table (#783, #422)", () => {
  it("says nothing for the client's own choice", () => {
    expect(targetFaultNote("client")).toBeNull();
    expect(targetFault("client")).toBeNull();
  });

  for (const [source, note] of Object.entries(TARGET_SOURCE_NOTES.tier)) {
    it(`CSF, ${source}`, () => {
      expect(targetFaultNote(source)).toBe(note);
    });
  }

  for (const [source, note] of Object.entries(TARGET_SOURCE_NOTES.stage)) {
    it(`ZT, ${source}`, () => {
      expect(targetFault(source)).toBe(note);
    });
  }

  it("reads an unknown source as the unrecognised row, never as nothing", () => {
    expect(targetFaultNote("client_from_a_future_build")).toBe(
      TARGET_SOURCE_NOTES.tier.unrecognised,
    );
    expect(targetFault("client_from_a_future_build")).toBe(
      TARGET_SOURCE_NOTES.stage.unrecognised,
    );
  });

  it("reads a source named like an Object method as unrecognised, not a function", () => {
    expect(targetFaultNote("toString")).toBe(
      TARGET_SOURCE_NOTES.tier.unrecognised,
    );
    expect(targetFault("constructor")).toBe(
      TARGET_SOURCE_NOTES.stage.unrecognised,
    );
  });

  it("derives the below-floor notes the workspaces render from the same rows", () => {
    expect(TIER_BELOW_FLOOR_NOTE).toBe(
      TARGET_SOURCE_NOTES.tier[BELOW_FLOOR_SOURCE],
    );
    expect(STAGE_BELOW_FLOOR_NOTE).toBe(
      TARGET_SOURCE_NOTES.stage[BELOW_FLOOR_SOURCE],
    );
  });

  it("has the same sources on both rungs", () => {
    expect(Object.keys(TARGET_SOURCE_NOTES.stage).sort()).toEqual(
      Object.keys(TARGET_SOURCE_NOTES.tier).sort(),
    );
  });
});
