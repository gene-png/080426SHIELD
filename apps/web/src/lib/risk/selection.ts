import type { RiskInclude, RiskSelectableService } from "./types";

/**
 * RR-1 (for #1122): the admin chooses which services feed the Risk Register.
 * Design note rev 12, §2 and §8; the copy is approved verbatim (#736
 * 6131606581, 6133670854). Labels are the server's (`label` on the gate's
 * rows and the register's lists), rendered as given.
 */

export const BLOCK_HEADING = "Inputs to include";
export const ZT_RADIO_LEGEND = "Zero Trust framework";
export const ZT_FRAMEWORK_OPTIONS: ReadonlyArray<{
  value: "cisa_ztmm_2_0" | "dod_ztra";
  label: string;
}> = [
  { value: "cisa_ztmm_2_0", label: "CISA ZTMM 2.0" },
  { value: "dod_ztra", label: "DoD ZT Reference Architecture" },
];
export const NEEDS_CSF_OR_ZT =
  "Choose NIST CSF, Zero Trust, or both. ATT&CK coverage alone is not enough for a register.";
export const CHOOSE_ZT_FRAMEWORK = "Choose a Zero Trust framework.";

/** Copy 2. */
export function requiredLabel(label: string): string {
  return `${label}, required`;
}

/** Copy 18: an engaged service with no assessment, shown disabled. */
export function noAssessmentLine(label: string): string {
  return `${label}: no assessment yet, so it cannot be included.`;
}

/** "A", "A and B", "A, B and C": the server's `join_labels`. */
export function joinLabels(labels: readonly string[]): string {
  if (labels.length <= 1) return labels.join("");
  return `${labels.slice(0, -1).join(", ")} and ${labels[labels.length - 1]}`;
}

export const SELECTION_NOT_RECORDED_LINE =
  "This register has no usable record of how its services were chosen or which were left out.";

/**
 * Copy 8, then 9a or 9b, then one 9c per service; or copy 11 alone when the
 * register has no usable record of its selection. The same lines, in the same
 * order, as the files' `selection_lines`.
 */
export function selectionLines(r: {
  selection_recorded?: boolean;
  covered_inputs?: string[];
  deselected_inputs?: string[];
  ineligible_inputs?: string[];
}): string[] {
  if (r.selection_recorded !== true) return [SELECTION_NOT_RECORDED_LINE];
  const lines = [
    `This register was generated from ${joinLabels(r.covered_inputs ?? [])}.`,
  ];
  const deselected = r.deselected_inputs ?? [];
  if (deselected.length === 1)
    lines.push(`${deselected[0]} was not included in this register.`);
  else if (deselected.length > 1)
    lines.push(`${joinLabels(deselected)} were not included in this register.`);
  for (const label of r.ineligible_inputs ?? [])
    lines.push(
      `${label} was engaged but had no assessment when this register was generated, so it is not in this register.`,
    );
  return lines;
}

/** The block's choices, before they become a request. */
export interface SelectionChoice {
  csf: boolean;
  zt: boolean;
  /** The radio's answer when two frameworks are eligible; null unanswered. */
  ztFramework: "cisa_ztmm_2_0" | "dod_ztra" | null;
}

export interface SelectionModel {
  attack: RiskSelectableService[];
  csf: RiskSelectableService | null;
  zt: RiskSelectableService[];
  ineligible: RiskSelectableService[];
  /** CSF is the only one of CSF and ZT eligible: its box is required. */
  csfRequired: boolean;
  /** ZT is the only one of CSF and ZT eligible: its box is required. */
  ztRequired: boolean;
}

export function selectionModel(
  eligible: readonly RiskSelectableService[],
  ineligible: readonly RiskSelectableService[],
): SelectionModel {
  const csf = eligible.find((s) => s.kind === "csf") ?? null;
  const zt = eligible.filter((s) => s.kind === "zt");
  return {
    attack: eligible.filter((s) => s.kind === "attack"),
    csf,
    zt,
    ineligible: [...ineligible],
    csfRequired: csf !== null && zt.length === 0,
    ztRequired: csf === null && zt.length > 0,
  };
}

/** Eligible means ticked by default (ruling 6130838759); the radio is not. */
export function defaultChoice(m: SelectionModel): SelectionChoice {
  return {
    csf: m.csf !== null,
    zt: m.zt.length > 0,
    ztFramework: null,
  };
}

/**
 * What Generate would send, or why it cannot: `needs_csf_or_zt` (copy 5a,
 * both unticked) or `zt_framework` (copy 17, the radio is unanswered while
 * the ZT box is ticked or required). A request is never built from a guess.
 */
export function includeFor(
  m: SelectionModel,
  c: SelectionChoice,
):
  | { ok: true; include: RiskInclude }
  | { ok: false; reason: "needs_csf_or_zt" | "zt_framework" } {
  const csf = m.csf !== null && (m.csfRequired || c.csf);
  const ztOn = m.zt.length > 0 && (m.ztRequired || c.zt);
  let zero_trust: RiskInclude["zero_trust"] = null;
  if (ztOn) {
    if (m.zt.length === 1) {
      zero_trust = m.zt[0].framework as RiskInclude["zero_trust"];
    } else if (c.ztFramework === null) {
      return { ok: false, reason: "zt_framework" };
    } else {
      zero_trust = c.ztFramework;
    }
  }
  if (!csf && zero_trust === null)
    return { ok: false, reason: "needs_csf_or_zt" };
  return { ok: true, include: { csf, zero_trust } };
}
