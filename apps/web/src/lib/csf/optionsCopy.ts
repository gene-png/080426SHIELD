/**
 * CSF Options 1 and 3: the screen copy, APPROVED by Gene (#736 6205956728),
 * as written in the text package (6204461502) under the number beside each
 * string, with the advisor's changes to C3 and E3 (6205425122 item 3). Plain
 * strings and the formatting they need, no other logic. Tests type their own
 * copies rather than importing these.
 */

import type { CsfCoverage, CsfEvidenceStatus } from "./types";

/** The five maturity levels by name (6202644525 item 1). The engine's
 * bands are `maturity_level` in apps/api/app/csf/playbook.py. */
export const LEVEL_NAMES: Readonly<Record<number, string>> = {
  1: "Ad hoc",
  2: "Developing",
  3: "Defined",
  4: "Managed",
  5: "Optimized",
};

/** A level's name. A value outside 1..5 is a defect upstream, so it throws
 * rather than render a made-up name. */
export function levelName(level: number): string {
  const name = LEVEL_NAMES[level];
  if (name === undefined) {
    throw new Error(`CSF level ${String(level)} has no name`);
  }
  return name;
}

/** The client's self-rating tiers by name, as the csf_score prompt and the
 * questionnaire name them. */
export const RATING_NAMES: Readonly<Record<number, string>> = {
  1: "Partial",
  2: "Risk Informed",
  3: "Repeatable",
  4: "Adaptive",
};

/** The FIPS 199 impact tiers, in the order every table lists them. */
export const IMPACT_TIERS: readonly (readonly [string, string])[] = [
  ["high", "High"],
  ["moderate", "Moderate"],
  ["low", "Low"],
];

/** C1: the Subcategory cell of a subcategory with no scored tier and no
 * notes, with the client's rating or without one. */
export function selfReportedLine(rating: number | null | undefined): string {
  if (rating == null) {
    return "Not answered: no rating and no notes, so not scored.";
  }
  const name = RATING_NAMES[rating];
  if (name === undefined) {
    throw new Error(`CSF self-rating ${String(rating)} has no name`);
  }
  return `Self-reported, not validated: Tier ${rating} (${name}). No notes, so not scored.`;
}

/** C1: a subcategory with notes and no scored tier. */
export const HAS_NOTES_NOT_SCORED = "Has notes, not scored yet.";

/** C2: the Enterprise and Gap cells of a subcategory with no scored tier,
 * and C12's word for a tier left out of the roll-up. */
export const NOT_SCORED = "Not scored";

/** C3: the coverage line, stated at zero too. */
export function coverageLine(c: CsfCoverage): string {
  return `${c.scored} of ${c.total} subcategories scored; ${c.notes_not_scored} with notes, not yet scored; ${c.self_reported} self-reported only, not validated; ${c.not_answered} not answered.`;
}

/** C4: the Run AI result card's no-notes line, in every mode. */
export function noNotesRunLine(n: number): string {
  return n === 1
    ? "1 row has no notes, so the AI did not score it. A row a consultant scored keeps its scores."
    : `${n} rows have no notes, so the AI did not score them. Rows a consultant scored keep their scores.`;
}

/** C5: the omitted-rows alert's second sentence. */
export const OMITTED_ROWS_STAY =
  "On a Playbook that was not scored before, those rows stay not scored.";

/** C10: the panel description. */
export const PANEL_DESCRIPTION =
  "AI suggests the dimensions; code computes every level and the roll-up.";

/** C11: the button. */
export const RUN_AI_LABEL = "Run AI";

/** Groups tiers by a value, in the table's tier order: `A (High, Low) · B
 * (Moderate)`, each group placed where its first tier falls. */
function groupByTier(entries: readonly (readonly [string, string])[]): string {
  const groups: { value: string; tiers: string[] }[] = [];
  for (const [tier, value] of entries) {
    const found = groups.find((g) => g.value === value);
    if (found) {
      found.tiers.push(tier);
    } else {
      groups.push({ value, tiers: [tier] });
    }
  }
  return groups.map((g) => `${g.value} (${g.tiers.join(", ")})`).join(" · ");
}

/** C12: the Tiers column, level names grouped by tier, with a tier left out
 * of the roll-up as `Not scored (Low)`. */
export function tiersByLevel(
  tierLevels: Readonly<Record<string, number>>,
  unscoredTiers: readonly string[],
): string {
  const entries: [string, string][] = [];
  for (const [key, label] of IMPACT_TIERS) {
    if (unscoredTiers.includes(key)) {
      entries.push([label, NOT_SCORED]);
    } else if (tierLevels[key] != null) {
      entries.push([label, levelName(tierLevels[key])]);
    }
  }
  return groupByTier(entries);
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

/** C8: the Evidence column of the panel, grouped by tier the way C12 groups
 * levels. */
export function evidenceByTier(
  tierEvidence: Readonly<Record<string, CsfEvidenceStatus>>,
): string {
  const words = Object.fromEntries(EVIDENCE_OPTIONS) as Record<
    CsfEvidenceStatus,
    string
  >;
  const entries: [string, string][] = [];
  for (const [key, label] of IMPACT_TIERS) {
    const value = tierEvidence[key];
    if (value != null) {
      entries.push([label, words[value]]);
    }
  }
  return groupByTier(entries);
}

/** C6: what the editor's level line adds for an evidence value. */
export const EVIDENCE_LEVEL_NOTE: Readonly<Record<CsfEvidenceStatus, string>> =
  {
    on_file: "",
    confirmed_in_discussion: "(confirmed in discussion; no evidence on file)",
    neither: "(not validated by evidence)",
  };

/** E2: the level from which a level with `neither` is notional (Managed). */
export const NOTIONAL_FROM_LEVEL = 4;

/** E2: the notional caveat. */
export function notionalCaveat(level: number): string {
  return `${levelName(level)} is notional: no evidence is on file and it was not confirmed in discussion.`;
}

/** E3: the evidence line beside C3, stated at zero too. */
export function evidenceLine(c: CsfCoverage): string {
  return `Of the ${c.scored} scored subcategories: ${c.evidence_on_file} with evidence on file for every scored tier; ${c.evidence_confirmed} confirmed in discussion (every scored tier on file or confirmed, at least one confirmed); ${c.evidence_mixed} mixed (at least one scored tier with neither, and at least one with evidence on file or confirmed); ${c.evidence_neither} with neither on any scored tier; ${c.notional} at Managed or Optimized are notional.`;
}
