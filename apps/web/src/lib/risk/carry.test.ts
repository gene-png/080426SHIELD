import { describe, expect, it } from "vitest";

import { carriedSentences } from "./carry";

describe("carriedSentences (#854 F3)", () => {
  it("says only what carried when nothing was lost", () => {
    expect(carriedSentences(1, 2, [], true)).toEqual([
      "1 consultant rating was carried over from version 2.",
    ]);
  });

  it("gives each reason its own sentence, counting RATINGS", () => {
    expect(
      carriedSentences(
        0,
        4,
        [
          { key: "T1003", reason: "ambiguous" },
          { key: "T1003", reason: "ambiguous" },
          { key: "GV.OC-01", reason: "no_entry" },
          { key: "Orphan risk", reason: "no_source_id" },
        ],
        true,
      ),
    ).toEqual([
      "0 consultant ratings were carried over from version 4.",
      "2 ratings could not be carried because this version or the last has more than one entry for the same finding: T1003, T1003. Rate them again in the Register table.",
      "1 rating could not be carried because this version has no entry for that finding: GV.OC-01.",
      '1 rating could not be carried because the entry named no finding: "Orphan risk".',
    ]);
  });

  it("offers no rate-again remedy when the new version has no entry", () => {
    const [, line] = carriedSentences(
      0,
      1,
      [
        { key: "T1059", reason: "no_entry" },
        { key: "T1003", reason: "no_entry" },
      ],
      true,
    );
    expect(line).toBe(
      "2 ratings could not be carried because this version has no entry for those findings: T1059, T1003.",
    );
    expect(line).not.toMatch(/Rate/);
  });
});
