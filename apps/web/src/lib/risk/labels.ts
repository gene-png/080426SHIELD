/**
 * The Risk Register's service and Zero Trust framework labels, for the web.
 *
 * The one web copy of the target and scope-key labels; `lib/risk/inputs.ts`
 * and `components/admin/zt/ZtWorkspace.tsx` repeat these strings (#946). They
 * mirror `_SERVICE_LABELS` and `ZT_FRAMEWORK_NAMES` in `app/risk/exporters.py`,
 * which label the same services in the client's PDF, Word file and workbook.
 * A Python dict cannot be shared with TypeScript, so this is a synchronization
 * rather than a derivation. Change both, or the files and the screens name an
 * assessment differently.
 *
 * Maps rather than object literals, so a key like "constructor" is not found
 * on the prototype: the Python `dict` lookups this mirrors see own keys only.
 */
export const SERVICE_LABELS: ReadonlyMap<string, string> = new Map([
  ["attack", "ATT&CK coverage"],
  ["csf", "NIST CSF"],
  ["zt", "Zero Trust"],
]);

/**
 * #876. The ZT frameworks by the names the ZT deliverable prints, so the
 * Risk Register names a framework the way the client's own Zero Trust report
 * does (advisor, #736 6019425290, Q3).
 */
export const ZT_FRAMEWORK_NAMES: ReadonlyMap<string, string> = new Map([
  ["cisa_ztmm_2_0", "CISA ZTMM 2.0"],
  ["dod_ztra", "DoD ZT Reference Architecture"],
]);

/** Python's `str.partition(":")`: split on the FIRST colon only. */
function partition(key: string): [kind: string, qualifier: string] {
  const at = key.indexOf(":");
  return at === -1 ? [key, ""] : [key.slice(0, at), key.slice(at + 1)];
}

/**
 * #403 / #876. A scope key's label, as `scope_label` in the export gives it,
 * for the scored-coverage banner: "zt" while a kind has one source,
 * "zt:<framework>" when it has two. An unknown key renders as itself: a row
 * that vanished from a disclosure would be the failure the disclosure exists
 * to prevent, and an ugly token is merely ugly. Target lines do NOT use this:
 * they name kind and framework from the stored record (`baseline.ts`).
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
