import { describe, expect, it } from "vitest";

import {
  type RiskTargetUsed,
  TARGETS_NOT_RECORDED,
  targetSentences,
} from "./baseline";

/**
 * #474. The expected lines are the approved table's strings, verbatim
 * (advisor, #736 6054419744, approving 6053630989). The framework is named
 * only when the record holds more than one Zero Trust entry (Q3, ruling 2a).
 */
function t(
  kind: string,
  framework: string | null,
  target: number,
  source: string,
): RiskTargetUsed {
  return { kind, framework, target, source, origin: "live_at_generate" };
}

const CSF_CLIENT_4 =
  "NIST CSF findings are measured against target tier 4, the engagement target when this register was generated.";
const CISA_CLIENT_4 =
  "Zero Trust (CISA ZTMM 2.0) findings are measured against target stage 4, the engagement target when this register was generated.";
const DOD_DEFAULT =
  "Zero Trust (DoD ZT Reference Architecture) findings are measured against target stage 3, SHIELD's default: no engagement target was set.";

describe("targetSentences (#474)", () => {
  it("one CSF, client 4", () => {
    expect(targetSentences([t("csf", null, 4, "client")], true)).toEqual([
      CSF_CLIENT_4,
    ]);
  });

  it("one CSF, none set, and one CSF, unusable", () => {
    expect(targetSentences([t("csf", null, 3, "default")], true)).toEqual([
      "NIST CSF findings are measured against target tier 3, SHIELD's default: no engagement target was set.",
    ]);
    expect(
      targetSentences([t("csf", null, 3, "client_out_of_range")], true),
    ).toEqual([
      "NIST CSF findings are measured against target tier 3, SHIELD's default: the engagement target could not be used.",
    ]);
  });

  it("one ZT (DoD, default): the framework is not named", () => {
    expect(targetSentences([t("zt", "dod_ztra", 3, "default")], true)).toEqual([
      "Zero Trust findings are measured against target stage 3, SHIELD's default: no engagement target was set.",
    ]);
  });

  it("CISA (client 4) plus DoD (default): each framework is named", () => {
    expect(
      targetSentences(
        [
          t("zt", "cisa_ztmm_2_0", 4, "client"),
          t("zt", "dod_ztra", 3, "default"),
        ],
        true,
      ),
    ).toEqual([CISA_CLIENT_4, DOD_DEFAULT]);
  });

  it("CSF plus CISA plus DoD: the CSF line, then the two ZT lines", () => {
    expect(
      targetSentences(
        [
          t("csf", null, 4, "client"),
          t("zt", "cisa_ztmm_2_0", 4, "client"),
          t("zt", "dod_ztra", 3, "default"),
        ],
        true,
      ),
    ).toEqual([CSF_CLIENT_4, CISA_CLIENT_4, DOD_DEFAULT]);
  });

  it("says not recorded rather than nothing, for false and for absent", () => {
    expect(targetSentences([], false)).toEqual([TARGETS_NOT_RECORDED]);
    expect(targetSentences(undefined, undefined)).toEqual([
      TARGETS_NOT_RECORDED,
    ]);
    expect(TARGETS_NOT_RECORDED).toBe(
      "The targets these findings were measured against were not recorded for this register.",
    );
  });
});
