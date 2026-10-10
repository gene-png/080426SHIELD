import { titleCase } from "@/lib/risk/matrix";

/**
 * #806 G1 option 3, as approved for both Risk screens (#736 6094620397, Risk
 * E item 4). Mirrors `_other_axes` and `OTHER_AXES_HEADER` in
 * `app/risk/exporters.py`, which render the same cell in the client's PDF,
 * Word file and workbook. A Python function cannot be shared with TypeScript,
 * so this is a synchronization rather than a derivation: change both.
 */
export const OTHER_AXES_HEADER = "Other axes";

/**
 * Three states, three renderings: `null` is "Not recorded" (an entry from
 * before migration 0066, or a model response with no readable list), `[]` is
 * an EMPTY cell (the claim "no other axis"), and a list is its axis display
 * names joined by ", ". `undefined` reads as `null`: a payload without the
 * field has recorded nothing, and missing data is never "none".
 */
export function otherAxesCell(
  axes: readonly string[] | null | undefined,
): string {
  if (axes === null || axes === undefined) return "Not recorded";
  return axes.map((a) => titleCase(a)).join(", ");
}
