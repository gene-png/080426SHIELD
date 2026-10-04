/**
 * #474. The sentences naming which target each service's findings were
 * measured against. ONE formatter for the consultant's screen and the client's
 * dashboard, with the same words the exported register prints
 * (`app/risk/exporters.py::_target_lines`) -- a register whose screen and PDF
 * named its baseline differently would read as two baselines.
 */
export interface RiskTargetUsed {
  service: string;
  target: number;
  source: string;
  origin: string;
}

const LABELS: Record<string, string> = {
  csf: "NIST CSF",
  zt: "Zero Trust",
};
const UNITS: Record<string, string> = { csf: "tier", zt: "stage" };

export const TARGETS_NOT_RECORDED =
  "The targets these findings were measured against were not recorded for this register.";

export function targetSentence(t: RiskTargetUsed): string {
  const why =
    t.source === "client"
      ? "the engagement target when this register was generated"
      : t.source === "default"
        ? "SHIELD's default: no engagement target was set"
        : "SHIELD's default: the engagement target could not be used";
  return `${LABELS[t.service] ?? t.service} findings are measured against target ${UNITS[t.service] ?? "level"} ${t.target}, ${why}.`;
}

/**
 * Three states. `recorded` undefined or false: the not-recorded sentence (a
 * response predating the field reads as not recorded, never as "no target").
 * Recorded: one sentence per service. Recorded with no service: nothing, as
 * there is no target to name.
 */
export function targetSentences(
  targets: RiskTargetUsed[] | undefined,
  recorded: boolean | undefined,
): string[] {
  if (recorded !== true) return [TARGETS_NOT_RECORDED];
  return (targets ?? []).map(targetSentence);
}
