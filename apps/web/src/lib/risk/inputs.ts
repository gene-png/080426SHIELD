import type { RiskInputState } from "./types";

/**
 * #737: the Inputs panel's words. Gene's line is his, verbatim (#736,
 * 5984159954); every other string is DRAFT copy, with the advisor.
 */
export const INPUTS_RULE =
  "This register is a draft until every assessment it draws on is final.";

const LABELS: Record<string, string> = {
  attack: "ATT&CK coverage",
  csf: "NIST CSF",
  zt: "Zero Trust",
  tech_debt: "Technology debt list",
};

const STATES: Record<string, string> = {
  released: "released",
  draft: "in progress (draft)",
  submitted: "submitted, not yet released",
  approved: "approved, not yet released",
};

export function inputLine(row: RiskInputState): string {
  const label = LABELS[row.kind] ?? row.kind;
  if (!row.engaged) return `${label}: not engaged`;
  if (row.status === null) return `${label}: not started`;
  return `${label}: ${STATES[row.status] ?? row.status}`;
}

/**
 * #554 R3, option (b): an entry whose ATT&CK technique's computed status
 * awaited review when the register was generated. DRAFT copy, with the
 * advisor; the export's source cell carries the same words.
 */
export const REVIEW_PENDING_NOTE = " (computed status awaiting review)";

export function sourceStateNote(state: string | null): string | null {
  return state ? ` (from a ${state} assessment)` : null;
}
