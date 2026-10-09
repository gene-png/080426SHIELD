import * as React from "react";

import type { ExtractionFinding } from "@/lib/tech_debt/types";

/**
 * #833 / #834: the values the extraction could not store as given -- a cost
 * that was not a number, a licence count that was not whole, a name longer than
 * its column. Each was left blank (a number) or shortened (a string), and the
 * list records it (`capability_lists.extraction_findings`).
 *
 * Copy approved on issue 833 (comments 5984037981 and 5995416506; 736 rulings
 * 5986057990 and the 14:05Z R3 approval). `field` uses the table's own labels.
 * `confidence_pct` and `source_row_index` are not editable in the table, so
 * they get their own line, which names no control.
 */

const LABELS: Record<string, string> = {
  name: "Name",
  vendor: "Vendor",
  category: "Category",
  function: "Function",
  annual_cost_usd: "Annual cost USD",
  license_count: "License count",
};

/** `app.tech_debt.extract.DUPLICATED`: two items naming one source row. */
const DUPLICATED = "duplicated";

/** Not editable in the table, so never under "Correct these in the table". */
const NOT_EDITABLE = new Set(["confidence_pct", "source_row_index"]);

function line(f: ExtractionFinding): string {
  const field = LABELS[f.field] ?? f.field;
  switch (f.reason) {
    case "unparseable":
      return `${f.item_name}, ${field}: "${f.value}" is not a number, so it was left blank.`;
    case "not_whole":
      return `${f.item_name}, ${field}: ${f.value} is not a whole number, so it was left blank.`;
    case "out_of_range":
      return `${f.item_name}, ${field}: ${f.value} is outside the allowed range, so it was left blank.`;
    case "truncated":
      return `${f.item_name}, ${field}: shortened to ${f.width} characters.`;
    case "rounded":
      // #878 review A3. Copy approved by the advisor (#736 comment 6020214342).
      return `${f.item_name}, ${field}: ${f.value} was rounded to whole cents.`;
    default:
      // A reason this screen does not know yet: said plainly, never dropped.
      return `${f.item_name}, ${field}: ${f.reason}.`;
  }
}

export function ExtractionFindings({
  findings,
  readOnly,
}: {
  findings: ExtractionFinding[] | null | undefined;
  readOnly: boolean;
}): React.ReactElement | null {
  // NULL is "not recorded" (a list from before the check): say nothing, rather
  // than imply nothing was found.
  if (!findings) return null;
  // C6 (for #806): a duplicated source row is a value KEPT as sent, not one
  // that could not be stored; `ExtractionFlags` says it, so it is not here.
  const shown = findings.filter((f) => f.reason !== DUPLICATED);
  if (shown.length === 0) return null;
  const editable = shown.filter((f) => !NOT_EDITABLE.has(f.field));
  const other = shown.length - editable.length;
  return (
    <div
      className="rounded-md border border-border bg-surface-sunken p-3 text-sm"
      data-testid="extraction-findings"
    >
      {editable.length > 0 ? (
        <>
          <p className="font-medium text-ink-primary">
            {editable.length === 1
              ? "1 value from the AI could not be stored as given:"
              : `${editable.length} values from the AI could not be stored as given:`}
          </p>
          <ul className="mt-1 list-disc pl-5 text-ink-secondary">
            {editable.map((f, i) => (
              <li key={`${f.item_name}-${f.field}-${i}`}>{line(f)}</li>
            ))}
          </ul>
          {readOnly ? null : (
            <p className="mt-1 text-ink-secondary">
              Correct these in the table below.
            </p>
          )}
        </>
      ) : null}
      {other > 0 ? (
        <p
          className="mt-1 text-ink-secondary"
          data-testid="extraction-findings-not-editable"
        >
          {other === 1
            ? "1 value about the AI's confidence or the source row could not be stored as given and was left blank."
            : `${other} values about the AI's confidence or the source row could not be stored as given and were left blank.`}
        </p>
      ) : null}
    </div>
  );
}
