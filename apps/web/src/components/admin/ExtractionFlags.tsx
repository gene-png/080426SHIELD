import * as React from "react";

import type { ExtractionFlagCounts } from "@/lib/tech_debt/types";

/**
 * C6, for #806: what Tech Debt prompt v3.2 closes and the AI still sent. Each
 * value was kept as the AI sent it; this says so, one line per non-zero count.
 * The rows are editable in the list below, and correcting one clears its count
 * (the api reads the first three live from the rows).
 *
 * E1 copy, PROPOSED in the #806 plan (issue 806, comment 5984600764) and NOT
 * yet approved: the advisor sees it before it ships. Every string lives in
 * `EXTRACTION_FLAG_COPY`, so a wording change is one edit there. The singular
 * forms are new with this build and go to the advisor with the rest.
 */

type FlagKey = keyof ExtractionFlagCounts;

export const EXTRACTION_FLAG_COPY: Record<
  FlagKey,
  { one: string; many: (n: number) => string }
> = {
  name_missing: {
    one: '1 row came back without a name and is listed as "Unknown capability".',
    many: (n) =>
      `${n} rows came back without a name and are listed as "Unknown capability".`,
  },
  confidence_off_scale: {
    one: "1 row came back with a confidence the extraction does not use (only 100, 90 or 60).",
    many: (n) =>
      `${n} rows came back with a confidence the extraction does not use (only 100, 90 or 60).`,
  },
  category_off_list: {
    one: "1 row came back with a category outside the standard list; it is kept as the AI wrote it.",
    many: (n) =>
      `${n} rows came back with a category outside the standard list; it is kept as the AI wrote it.`,
  },
  source_row_duplicated: {
    one: "1 source row was turned into more than one capability.",
    many: (n) => `${n} source rows were turned into more than one capability.`,
  },
};

/** The order the lines render in: the plan's order. */
const ORDER: FlagKey[] = [
  "name_missing",
  "confidence_off_scale",
  "category_off_list",
  "source_row_duplicated",
];

export function extractionFlagLine(key: FlagKey, n: number): string {
  const copy = EXTRACTION_FLAG_COPY[key];
  return n === 1 ? copy.one : copy.many(n);
}

export function ExtractionFlags({
  flags,
}: {
  flags: ExtractionFlagCounts | null | undefined;
}): React.ReactElement | null {
  // Null is "not measured" (an earlier prompt's list): say nothing, rather
  // than imply nothing was found.
  if (!flags) return null;
  const shown = ORDER.filter((k) => flags[k] > 0);
  if (shown.length === 0) return null;
  return (
    <ul
      className="list-disc rounded-md border border-border bg-surface-sunken p-3 pl-8 text-sm text-ink-secondary"
      data-testid="extraction-flags"
    >
      {shown.map((k) => (
        <li key={k} data-testid={`extraction-flag-${k}`}>
          {extractionFlagLine(k, flags[k])}
        </li>
      ))}
    </ul>
  );
}
