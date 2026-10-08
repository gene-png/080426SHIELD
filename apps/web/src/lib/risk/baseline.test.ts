import { describe, expect, it } from "vitest";

import { TARGETS_NOT_RECORDED, targetSentences } from "./baseline";

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

  it("says not recorded rather than nothing, for false and for absent", () => {
    expect(targetSentences([], false)).toEqual([TARGETS_NOT_RECORDED]);
    expect(targetSentences(undefined, undefined)).toEqual([
      TARGETS_NOT_RECORDED,
    ]);
  });
});
