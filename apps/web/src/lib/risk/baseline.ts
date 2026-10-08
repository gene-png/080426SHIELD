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

/**
 * #876: with two Zero Trust services the key is "zt:<framework>". The client
 * dashboard has no link-scope label function to reuse, so this is a PORT of
 * `scope_label` in `app/risk/exporters.py` (the export's own labeller) and of
 * `scopeLabel` in `components/admin/risk/RiskRegisterDashboard.tsx`, with the
 * same two framework names. Change all three together, or the client's PDF
 * and this screen name a framework differently.
 */
const ZT_FRAMEWORK_NAMES: Record<string, string> = {
  cisa_ztmm_2_0: "CISA ZTMM 2.0",
  dod_ztra: "DoD ZT Reference Architecture",
};

function scopeLabel(key: string): string {
  const known = LABELS[key];
  if (known !== undefined) return known;
  const [kind, qualifier] = key.split(":", 2);
  const kindLabel = LABELS[kind];
  const fw =
    qualifier === undefined ? undefined : ZT_FRAMEWORK_NAMES[qualifier];
  return kindLabel !== undefined && fw !== undefined
    ? `${kindLabel} (${fw})`
    : key;
}

/** The unit is the KIND's, so a framework-qualified key keeps "stage". */
function unitOf(key: string): string {
  return UNITS[key.split(":", 1)[0]] ?? "level";
}

export const TARGETS_NOT_RECORDED =
  "The targets these findings were measured against were not recorded for this register.";

export function targetSentence(t: RiskTargetUsed): string {
  const why =
    t.source === "client"
      ? "the engagement target when this register was generated"
      : t.source === "default"
        ? "SHIELD's default: no engagement target was set"
        : "SHIELD's default: the engagement target could not be used";
  return `${scopeLabel(t.service)} findings are measured against target ${unitOf(t.service)} ${t.target}, ${why}.`;
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
