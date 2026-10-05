/**
 * #854 F3. The sentences disclosing what a regenerate carried over, and why
 * each consultant rating it could not carry was not carried. One item per
 * RATING (never per finding), so every count is a count of ratings.
 *
 * The three reasons get DIFFERENT sentences, because only one of them has a
 * remedy: an ambiguous match can be rated again by hand, while a finding the
 * new version has no entry for has nothing to rate (#854 round 4). A title
 * (no source id) is quoted, so it cannot be mistaken for a finding code.
 */
export interface RatingNotCarried {
  key: string;
  reason: "ambiguous" | "no_entry" | "no_source_id";
}

function ratings(n: number): string {
  return n === 1 ? "1 rating" : `${n} ratings`;
}

export function carriedSentences(
  carried: number,
  fromVersion: number,
  notCarried: RatingNotCarried[],
): string[] {
  const lines = [
    `${carried} consultant ${carried === 1 ? "rating was" : "ratings were"} carried over from version ${fromVersion}.`,
  ];
  const keys = (reason: RatingNotCarried["reason"]) =>
    notCarried.filter((r) => r.reason === reason).map((r) => r.key);

  const ambiguous = keys("ambiguous");
  if (ambiguous.length > 0) {
    lines.push(
      `${ratings(ambiguous.length)} could not be carried because this version or the last has more than one entry for the same finding: ${ambiguous.join(", ")}. Rate ${ambiguous.length === 1 ? "it" : "them"} again in the Register table.`,
    );
  }
  const noEntry = keys("no_entry");
  if (noEntry.length > 0) {
    lines.push(
      `${ratings(noEntry.length)} could not be carried because this version has no entry for ${noEntry.length === 1 ? "that finding" : "those findings"}: ${noEntry.join(", ")}.`,
    );
  }
  const noSource = keys("no_source_id");
  if (noSource.length > 0) {
    lines.push(
      `${ratings(noSource.length)} could not be carried because the entry named no finding: ${noSource.map((t) => `"${t}"`).join(", ")}.`,
    );
  }
  return lines;
}
