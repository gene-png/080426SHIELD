import { SERVICE_LABELS, ZT_FRAMEWORK_NAMES } from "./labels";

/**
 * #474. The sentences naming which target each service's findings were
 * measured against. ONE formatter for the consultant's screen and the client's
 * dashboard, with the same words the exported register prints
 * (`app/risk/exporters.py::_target_lines`) -- a register whose screen and PDF
 * named its baseline differently would read as two baselines.
 *
 * `kind` and `framework` say which service (`framework` is the ZT framework,
 * null for CSF). The stored scope key is never sent, so nothing can render it.
 */
export interface RiskTargetUsed {
  kind: string;
  framework: string | null;
  /** #474 D': null for a CSF record measured against the Playbook. */
  target: number | null;
  source: string;
  origin: string;
}

/** #474. Which word each kind's target takes; `_TARGET_UNITS` in the export. */
const TARGET_UNITS: ReadonlyMap<string, string> = new Map([
  ["csf", "tier"],
  ["zt", "stage"],
]);

/**
 * What a target line calls a service, as `target_label` in the export: the
 * kind's label, and the ZT framework only when the record holds more than one
 * ZT entry (Q3, ruling 2a). A label this module lacks renders as the token
 * the API sent, never as nothing; the API sends only kinds and frameworks its
 * reader validated.
 */
function targetLabel(t: RiskTargetUsed, nameFramework: boolean): string {
  const label = SERVICE_LABELS.get(t.kind) ?? t.kind;
  if (!nameFramework || t.framework === null) return label;
  return `${label} (${ZT_FRAMEWORK_NAMES.get(t.framework) ?? t.framework})`;
}

export const TARGETS_NOT_RECORDED =
  "The targets these findings were measured against were not recorded for this register.";

/**
 * #474 D' (Gene, #736 5984218862): CSF findings are measured against each
 * subcategory's Playbook target, so the record names no single target.
 * Approved verbatim (#736 6087027524, Q1); `_target_lines` prints the same.
 */
const PLAYBOOK_SOURCE = "playbook";

export function targetSentence(
  t: RiskTargetUsed,
  nameFramework: boolean,
): string {
  if (t.source === PLAYBOOK_SOURCE) {
    return `${targetLabel(t, nameFramework)} findings are measured against each subcategory's target level in the CSF Playbook.`;
  }
  const why =
    t.source === "client"
      ? "the engagement target when this register was generated"
      : t.source === "default"
        ? "SHIELD's default: no engagement target was set"
        : "SHIELD's default: the engagement target could not be used";
  return `${targetLabel(t, nameFramework)} findings are measured against target ${TARGET_UNITS.get(t.kind) ?? "level"} ${t.target}, ${why}.`;
}

/**
 * Two states. `recorded` undefined or false: the not-recorded sentence (a
 * response predating the field reads as not recorded, never as "no target").
 * Recorded: one sentence per service, in the API's order (sorted by kind,
 * then framework). A recorded record always holds a CSF or ZT entry: generate
 * requires one, and the API reads an empty record as not recorded (ruling 2d).
 */
export function targetSentences(
  targets: RiskTargetUsed[] | undefined,
  recorded: boolean | undefined,
): string[] {
  if (recorded !== true) return [TARGETS_NOT_RECORDED];
  const rows = targets ?? [];
  const nameFramework = rows.filter((t) => t.kind === "zt").length > 1;
  return rows.map((t) => targetSentence(t, nameFramework));
}
