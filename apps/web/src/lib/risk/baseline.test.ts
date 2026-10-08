import { describe, expect, it } from "vitest";

import {
  TARGETS_NOT_RECORDED,
  scopeLabel,
  targetSentences,
  unitOf,
} from "./baseline";

/**
 * Expected values PRINTED BY the Python labeller, `scope_label` and
 * `_TARGET_UNITS.get(key.partition(":")[0], "level")` in
 * `app/risk/exporters.py`, run over these keys on 2026-10-08. Not read from
 * this module's constants: the point is that the screen and the PDF agree.
 */
const PYTHON_SCOPE_LABELS: [key: string, label: string, unit: string][] = [
  ["csf", "NIST CSF", "tier"],
  ["zt", "Zero Trust", "stage"],
  ["attack", "ATT&CK coverage", "level"],
  ["zt:cisa_ztmm_2_0", "Zero Trust (CISA ZTMM 2.0)", "stage"],
  ["zt:dod_ztra", "Zero Trust (DoD ZT Reference Architecture)", "stage"],
  ["zt:unknown", "zt:unknown", "stage"],
  ["zt:dod_ztra:x", "zt:dod_ztra:x", "stage"],
  ["constructor", "constructor", "level"],
  // The framework-name lookup is own-key only too: an object literal would
  // turn this into "Zero Trust (function Object() ...)".
  ["zt:constructor", "zt:constructor", "stage"],
];

describe("scopeLabel and unitOf match the export's labeller", () => {
  it.each(PYTHON_SCOPE_LABELS)("%s -> %s, %s", (key, label, unit) => {
    expect(scopeLabel(key)).toBe(label);
    expect(unitOf(key)).toBe(unit);
  });
});

describe("targetSentences (#474)", () => {
  it("names each service's target and why, in the export's words", () => {
    expect(
      targetSentences(
        [
          {
            service: "csf",
            target: 4,
            source: "client",
            origin: "live_at_generate",
          },
          {
            service: "zt",
            target: 3,
            source: "default",
            origin: "live_at_generate",
          },
        ],
        true,
      ),
    ).toEqual([
      "NIST CSF findings are measured against target tier 4, the engagement target when this register was generated.",
      "Zero Trust findings are measured against target stage 3, SHIELD's default: no engagement target was set.",
    ]);
  });

  it("says an unusable target fell back to the default", () => {
    expect(
      targetSentences(
        [
          {
            service: "csf",
            target: 3,
            source: "client_out_of_range",
            origin: "live_at_generate",
          },
        ],
        true,
      ),
    ).toEqual([
      "NIST CSF findings are measured against target tier 3, SHIELD's default: the engagement target could not be used.",
    ]);
  });

  it("names each Zero Trust framework when two are engaged (#876 scope keys)", () => {
    // The keys the API sends for a client with both ZT services
    // (`test_risk_baseline_disclosure.py`), labelled the way the scored-
    // coverage line labels them, with the ZT unit.
    expect(
      targetSentences(
        [
          {
            service: "zt:cisa_ztmm_2_0",
            target: 3,
            source: "default",
            origin: "live_at_generate",
          },
          {
            service: "zt:dod_ztra",
            target: 2,
            source: "client",
            origin: "live_at_generate",
          },
        ],
        true,
      ),
    ).toEqual([
      "Zero Trust (CISA ZTMM 2.0) findings are measured against target stage 3, SHIELD's default: no engagement target was set.",
      "Zero Trust (DoD ZT Reference Architecture) findings are measured against target stage 2, the engagement target when this register was generated.",
    ]);
  });

  it("says nothing for a record of no targets (no CSF or ZT input)", () => {
    expect(targetSentences([], true)).toEqual([]);
  });

  it("says not recorded rather than nothing, for false and for absent", () => {
    expect(targetSentences([], false)).toEqual([TARGETS_NOT_RECORDED]);
    expect(targetSentences(undefined, undefined)).toEqual([
      TARGETS_NOT_RECORDED,
    ]);
  });
});
