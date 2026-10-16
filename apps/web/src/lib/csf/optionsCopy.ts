/**
 * CSF Options 1 and 3 (Gene, #736 6200638511; Q1 to Q4 approved in
 * 6201691989): the screen copy this change needs.
 *
 * PENDING GENE'S VERBATIM APPROVAL. Each string is worded as proposed in the
 * text package (#736 6204461502) under the number beside it, and is swapped
 * for the approved text in one commit. Plain strings, no logic.
 */

import type { CsfCoverage, CsfEvidenceStatus } from "./types";

/** C3: the coverage line, stated at zero too, with the fourth count the
 * advisor recommended for Q-A (#736 6205425122 item 3). */
export function coverageLine(c: CsfCoverage): string {
  return `${c.scored} of ${c.total} subcategories scored; ${c.notes_not_scored} with notes, not yet scored; ${c.self_reported} self-reported only, not validated; ${c.not_answered} not answered.`;
}

/** E3: the evidence line beside C3, approved verbatim (#736 6205956728),
 * stated at zero too. */
export function evidenceLine(c: CsfCoverage): string {
  return `Of the ${c.scored} scored subcategories: ${c.evidence_on_file} with evidence on file for every scored tier; ${c.evidence_confirmed} confirmed in discussion (every scored tier on file or confirmed, at least one confirmed); ${c.evidence_mixed} mixed (at least one scored tier with neither, and at least one with evidence on file or confirmed); ${c.evidence_neither} with neither on any scored tier; ${c.notional} at Managed or Optimized are notional.`;
}

/** E1: the evidence control's label and its three options. */
export const EVIDENCE_LABEL = "Evidence";
export const EVIDENCE_OPTIONS: readonly (readonly [
  CsfEvidenceStatus,
  string,
])[] = [
  ["on_file", "Evidence on file"],
  ["confirmed_in_discussion", "Confirmed in discussion"],
  ["neither", "Neither"],
];
