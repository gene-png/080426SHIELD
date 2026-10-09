import { describe, expect, it } from "vitest";

import { carriedSentences } from "./carry";

/**
 * #743, swept by shape into `carry.ts`: one item per RATING, and each rating
 * belongs to its own entry, so two ratings whose entries named no finding are
 * two entries, not "the entry". Reachable from `generate` after a version in
 * which two consultant-rated entries had their `source_id` dropped.
 */
describe("carriedSentences count nouns (#743)", () => {
  it("one rating whose entry named no finding", () => {
    const [, line] = carriedSentences(
      0,
      2,
      [{ key: "Orphan risk", reason: "no_source_id" }],
      true,
    );
    expect(line).toBe(
      '1 rating could not be carried because the entry named no finding: "Orphan risk".',
    );
  });

  it("two ratings whose entries named no finding", () => {
    const [, line] = carriedSentences(
      0,
      2,
      [
        { key: "Orphan risk", reason: "no_source_id" },
        { key: "Second orphan", reason: "no_source_id" },
      ],
      true,
    );
    expect(line).toBe(
      '2 ratings could not be carried because each entry named no finding: "Orphan risk", "Second orphan".',
    );
  });
});
