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

/**
 * Service tokens as the API spells them (#403), and (#876) the Zero Trust
 * frameworks by the names the ZT deliverable prints, for the scope keys the
 * Risk Register records: "zt" while a kind has one source, "zt:<framework>"
 * when it has two.
 *
 * THE ONE WEB COPY of `_SERVICE_LABELS`, `ZT_FRAMEWORK_NAMES` and
 * `scope_label` in `app/risk/exporters.py`, which label the same keys in the
 * client's PDF, Word file and workbook. A Python dict cannot be shared with
 * TypeScript, so this is a synchronization rather than a derivation. Change
 * both, or the files and the screens name an assessment differently.
 * `lib/risk/baseline.test.ts` pins this module to values the Python printed.
 *
 * Maps rather than object literals, so a key like "constructor" is not found
 * on the prototype: the Python `dict` lookups this mirrors see own keys only.
 */
const SERVICE_LABELS: ReadonlyMap<string, string> = new Map([
  ["attack", "ATT&CK coverage"],
  ["csf", "NIST CSF"],
  ["zt", "Zero Trust"],
]);

const ZT_FRAMEWORK_NAMES: ReadonlyMap<string, string> = new Map([
  ["cisa_ztmm_2_0", "CISA ZTMM 2.0"],
  ["dod_ztra", "DoD ZT Reference Architecture"],
]);

/** #474. The word each kind's target takes; `_TARGET_UNITS` in the export. */
const UNITS: ReadonlyMap<string, string> = new Map([
  ["csf", "tier"],
  ["zt", "stage"],
]);

/** Python's `str.partition(":")`: split on the FIRST colon only. */
function partition(key: string): [kind: string, qualifier: string] {
  const at = key.indexOf(":");
  return at === -1 ? [key, ""] : [key.slice(0, at), key.slice(at + 1)];
}

/**
 * A scope key's label, as `scope_label` gives it. An unknown key renders as
 * itself: a row that vanished from a disclosure would be the failure the
 * disclosure exists to prevent, and an ugly token is merely ugly.
 */
export function scopeLabel(key: string): string {
  const known = SERVICE_LABELS.get(key);
  if (known !== undefined) return known;
  const [kind, qualifier] = partition(key);
  const kindLabel = SERVICE_LABELS.get(kind);
  const fw = ZT_FRAMEWORK_NAMES.get(qualifier);
  return kindLabel !== undefined && fw !== undefined
    ? `${kindLabel} (${fw})`
    : key;
}

/** The unit is the KIND's, so a framework-qualified key keeps "stage". */
export function unitOf(key: string): string {
  return UNITS.get(partition(key)[0]) ?? "level";
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
