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

/**
 * The panel's word for a record status. Exported so the duplicate banner's
 * line (#896 B1) says what the panel says, by calling this rather than
 * copying the table.
 */
export function statusWord(status: string): string {
  return STATES[status] ?? status;
}

export function inputLine(row: RiskInputState): string {
  // #876: the framework (or service title) only when a kind has more than
  // one row; the server decides, so the screen and the refusal agree.
  const base = LABELS[row.kind] ?? row.kind;
  const label = row.qualifier ? `${base} (${row.qualifier})` : base;
  if (!row.engaged) return `${label}: not engaged`;
  if (row.status === null) return `${label}: not started`;
  // #474 D' (Gene, #736 5984218862): a released CSF record with no in-scope
  // Playbook rows feeds no CSF finding. Said only after "released" (#736
  // 6087027524, Q3): Risk reads only released CSF.
  const noPlaybook =
    row.status === "released" && row.no_playbook_scores === true
      ? ", no Playbook scores"
      : "";
  return `${label}: ${statusWord(row.status)}${noPlaybook}`;
}

/**
 * #554 R3, option (b): an entry whose ATT&CK technique's computed status
 * awaited review when the register was generated. DRAFT copy, with the
 * advisor; the export's source cell carries the same words.
 */
export const REVIEW_PENDING_NOTE = " (computed status awaiting review)";

export function sourceStateNote(state: string | null): string | null {
  if (!state) return null;
  // "an" before a vowel ("from an approved assessment"); the export's source
  // cell applies the same rule. {state} is the stored status: draft,
  // submitted or approved.
  const article = /^[aeiou]/i.test(state) ? "an" : "a";
  return ` (from ${article} ${state} assessment)`;
}
