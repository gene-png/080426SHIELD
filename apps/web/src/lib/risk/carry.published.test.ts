import { describe, expect, it } from "vitest";

import { carriedSentences, type RatingNotCarried } from "./carry";

/**
 * #930, option A (advisor, #736 6067815887, on the plan in 6067131971). Once a
 * version is published its ratings are fixed: the Register table's selects are
 * gone and `edit_entry_rating` answers 409, so the ambiguous line drops its
 * "Rate it/them again" imperative (D-076) and does not repeat the card above.
 * The draft wording is unchanged, byte for byte. Expected text is the approved
 * copy, verbatim.
 */
const AMBIGUOUS_ONE: RatingNotCarried[] = [
  { key: "T1003", reason: "ambiguous" },
];
const AMBIGUOUS_TWO: RatingNotCarried[] = [
  { key: "T1003", reason: "ambiguous" },
  { key: "T1004", reason: "ambiguous" },
];

describe("carriedSentences on a published version (#930)", () => {
  it("drops the imperative, singular", () => {
    const [, line] = carriedSentences(0, 2, AMBIGUOUS_ONE, false);
    expect(line).toBe(
      "1 rating could not be carried because this version or the last has more than one entry for the same finding: T1003.",
    );
    expect(line).not.toMatch(/Rate/);
    expect(line).not.toMatch(/Register table/);
  });

  it("drops the imperative, plural", () => {
    const [, line] = carriedSentences(0, 2, AMBIGUOUS_TWO, false);
    expect(line).toBe(
      "2 ratings could not be carried because this version or the last has more than one entry for the same finding: T1003, T1004.",
    );
    expect(line).not.toMatch(/Rate/);
    expect(line).not.toMatch(/Register table/);
  });

  it("keeps the draft wording byte for byte", () => {
    expect(carriedSentences(0, 2, AMBIGUOUS_ONE, true)[1]).toBe(
      "1 rating could not be carried because this version or the last has more than one entry for the same finding: T1003. Rate it again in the Register table.",
    );
    expect(carriedSentences(0, 2, AMBIGUOUS_TWO, true)[1]).toBe(
      "2 ratings could not be carried because this version or the last has more than one entry for the same finding: T1003, T1004. Rate them again in the Register table.",
    );
  });

  it("changes nothing else: the other two reasons and the carried line", () => {
    const rest: RatingNotCarried[] = [
      { key: "GV.OC-01", reason: "no_entry" },
      { key: "Orphan risk", reason: "no_source_id" },
    ];
    expect(carriedSentences(3, 2, rest, false)).toEqual(
      carriedSentences(3, 2, rest, true),
    );
  });
});
