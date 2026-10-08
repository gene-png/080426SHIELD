import { describe, expect, it } from "vitest";

import { scopeLabel } from "./labels";

/**
 * Expected labels PRINTED BY the Python labeller, `scope_label` in
 * `app/risk/exporters.py`, run over these keys on 2026-10-08. Not read from
 * this module's constants: the point is that the screen and the PDF agree.
 */
const PYTHON_SCOPE_LABELS: [key: string, label: string][] = [
  ["csf", "NIST CSF"],
  ["zt", "Zero Trust"],
  ["attack", "ATT&CK coverage"],
  ["zt:cisa_ztmm_2_0", "Zero Trust (CISA ZTMM 2.0)"],
  ["zt:dod_ztra", "Zero Trust (DoD ZT Reference Architecture)"],
  ["zt:unknown", "zt:unknown"],
  ["zt:dod_ztra:x", "zt:dod_ztra:x"],
  ["constructor", "constructor"],
  // The framework-name lookup is own-key only too: an object literal would
  // turn this into "Zero Trust (function Object() ...)".
  ["zt:constructor", "zt:constructor"],
];

describe("scopeLabel matches the export's scope_label", () => {
  it.each(PYTHON_SCOPE_LABELS)("%s -> %s", (key, label) => {
    expect(scopeLabel(key)).toBe(label);
  });
});
