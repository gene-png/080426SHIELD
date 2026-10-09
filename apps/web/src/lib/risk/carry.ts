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

/**
 * `editable` is whether this version's ratings can still be changed: true on
 * a draft, false once published (`finalized_at` set), when the Register
 * table's selects are gone and `edit_entry_rating` answers 409. REQUIRED, not
 * defaulted, so no caller can fail open into naming a control that is not
 * there (#930, D-076; option A, #736 6067815887): the published sentence drops
 * the imperative and does not repeat the card above it.
 */
export function carriedSentences(
  carried: number,
  fromVersion: number,
  notCarried: RatingNotCarried[],
  editable: boolean,
): string[] {
  const lines = [
    `${carried} consultant ${carried === 1 ? "rating was" : "ratings were"} carried over from version ${fromVersion}.`,
  ];
  const keys = (reason: RatingNotCarried["reason"]) =>
    notCarried.filter((r) => r.reason === reason).map((r) => r.key);

  const ambiguous = keys("ambiguous");
  if (ambiguous.length > 0) {
    lines.push(
      `${ratings(ambiguous.length)} could not be carried because this version or the last has more than one entry for the same finding: ${ambiguous.join(", ")}.` +
        (editable
          ? ` Rate ${ambiguous.length === 1 ? "it" : "them"} again in the Register table.`
          : ""),
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
      // #743: one rating per entry, so two ratings are two entries.
      `${ratings(noSource.length)} could not be carried because ${noSource.length === 1 ? "the entry" : "each entry"} named no finding: ${noSource.map((t) => `"${t}"`).join(", ")}.`,
    );
  }
  return lines;
}
