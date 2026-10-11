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
 * subcategory's Playbook target, so the record names no single target. The
 * recorded source token says which of the Playbook's three states it was in
 * (advisor, #736 6087786886, item 4); for the two that measure nothing the CSF
 * line is replaced. Approved verbatim: #736 6087027524 (Q1) and 6087786886
 * (item 4). `_PLAYBOOK_LINES` in the export prints the same words. Where the
 * Playbook had scores and targets that never shared a row (R11, #736
 * 6103383277), the files and both dashboards print `NO_SHARED_ROW_LINE`
 * instead of the no-scores line (#736 6104067136); the register response's
 * `csf_no_shared_row` says which, read by the files' own reader.
 */
const PLAYBOOK_LINES: ReadonlyMap<string, (label: string) => string> = new Map([
  [
    "playbook",
    (label: string) =>
      `${label} findings are measured against each subcategory's target level in the CSF Playbook.`,
  ],
  [
    "playbook_no_targets",
    (label: string) =>
      `${label} was not measured for this register: the CSF Playbook has no target levels set.`,
  ],
  [
    "playbook_no_scores",
    (label: string) =>
      `${label} was not measured for this register: the CSF Playbook has no scores.`,
  ],
]);

/** R11 (#736 6103383277), verbatim: `_PLAYBOOK_NO_SHARED_ROW_LINE` in the export. */
const NO_SHARED_ROW_LINE = (label: string) =>
  `${label} was not measured for this register: no CSF Playbook row has both a score and a target.`;

export function targetSentence(
  t: RiskTargetUsed,
  nameFramework: boolean,
  csfNoSharedRow: boolean = false,
): string {
  if (t.source === "playbook_no_scores" && csfNoSharedRow)
    return NO_SHARED_ROW_LINE(targetLabel(t, nameFramework));
  const playbook = PLAYBOOK_LINES.get(t.source);
  if (playbook) return playbook(targetLabel(t, nameFramework));
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
  csfNoSharedRow: boolean | undefined = false,
): string[] {
  if (recorded !== true) return [TARGETS_NOT_RECORDED];
  const rows = targets ?? [];
  const nameFramework = rows.filter((t) => t.kind === "zt").length > 1;
  return rows.map((t) =>
    targetSentence(t, nameFramework, csfNoSharedRow === true),
  );
}
