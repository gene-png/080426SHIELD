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

function rowLabel(row: RiskInputState): string {
  // #876: the framework (or service title) only when a kind has more than
  // one row; the server decides, so the screen and the refusal agree.
  const base = LABELS[row.kind] ?? row.kind;
  return row.qualifier ? `${base} (${row.qualifier})` : base;
}

/**
 * RR-1 (for #1122), design note §6.5 and §8 copy 13: the panel's second
 * group, for services that are NOT part of the register on screen and so do
 * not hold it in draft.
 */
export const NOT_IN_REGISTER_HEADING = "Not in this register";

/** Whether a row belongs under `NOT_IN_REGISTER_HEADING`. */
export function isNotInRegister(row: RiskInputState): boolean {
  return row.in_register === "deselected" || row.in_register === "ineligible";
}

/**
 * Copies 14 and 15: the fragment that replaces the status for a row not in
 * the register. Its record status is not shown, so "in progress (draft)"
 * never appears beside a service that does not hold the register in draft.
 */
export function notInRegisterLine(row: RiskInputState): string {
  return row.in_register === "deselected"
    ? `${rowLabel(row)}: left out of this register`
    : `${rowLabel(row)}: no assessment when this register was generated`;
}

export function inputLine(row: RiskInputState): string {
  const label = rowLabel(row);
  if (!row.engaged) return `${label}: not engaged`;
  if (row.status === null) return `${label}: not started`;
  // #474 D' (Gene, #736 5984218862): a released CSF record whose in-scope
  // Playbook rows record nothing but targets feeds no CSF finding (#736
  // 6101751588). Said only after "released" (#736 6087027524, Q3): Risk reads
  // only released CSF.
  // R11 (#736 6103383277): scores and targets that never share a row get
  // their own fragment; the server sets at most one of the two flags.
  const noPlaybook =
    row.status !== "released"
      ? ""
      : row.no_playbook_scores === true
        ? ", no Playbook scores"
        : row.no_shared_playbook_row === true
          ? ", no Playbook row with both a score and a target"
          : "";
  const unscored =
    row.status === "released"
      ? unscoredTargetsSentence(row.unscored_targeted_subcategories ?? 0)
      : null;
  // The tail is built OUTSIDE the template on purpose: a template nested
  // inside the one holding `row.status` reads to the "no surface puts an HTTP
  // status in a sentence" gate as prose around a status. `row.status` here is
  // the record status ("released"), never HTTP; the copy is unchanged.
  const tail = unscored ? ". " + unscored : "";
  return `${label}: ${statusWord(row.status)}${noPlaybook}${tail}`;
}

/**
 * R10 (#736 6102665946), reworded by R11 (#736 6103383277), approved verbatim
 * with its singular: targeted CSF
 * subcategories with no tier row both scored and targeted. The files print the
 * API's own sentence (`risk/csf_source.py`); null when n is 0.
 */
export function unscoredTargetsSentence(n: number): string | null {
  if (n === 1)
    return "1 targeted subcategory has no row with both a score and a target, and raises no finding.";
  if (n > 1)
    return `${n} targeted subcategories have no row with both a score and a target, and raise no finding.`;
  return null;
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
