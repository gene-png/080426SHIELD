import { describe, expect, it } from "vitest";

import { otherAxesDroppedNote } from "./otherAxes";

/**
 * Ruling #736 6105137014: the consultant's note for unreadable `other_axes`
 * tokens, approved copy with its plural. Only `invalid` drops count: a
 * duplicate or the primary axis repeated loses nothing.
 */
describe("otherAxesDroppedNote (#736 6105137014)", () => {
  it("states one unreadable axis", () => {
    expect(otherAxesDroppedNote({ invalid: 1 })).toBe(
      "1 AI-suggested axis could not be read and was dropped.",
    );
  });

  it("states several unreadable axes", () => {
    expect(otherAxesDroppedNote({ invalid: 3, duplicate: 1 })).toBe(
      "3 AI-suggested axes could not be read and were dropped.",
    );
  });

  it("says nothing for none, redundant drops only, not recorded, or absent", () => {
    expect(otherAxesDroppedNote({})).toBeNull();
    expect(otherAxesDroppedNote({ duplicate: 2, repeats_axis: 1 })).toBeNull();
    expect(otherAxesDroppedNote(null)).toBeNull();
    expect(otherAxesDroppedNote(undefined)).toBeNull();
  });
});
