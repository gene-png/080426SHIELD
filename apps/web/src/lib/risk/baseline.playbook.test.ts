import { describe, expect, it } from "vitest";

import { type RiskTargetUsed, targetSentences } from "./baseline";

/**
 * #474 D' (Gene, #736 5984218862): Risk's CSF findings are measured against
 * each subcategory's Playbook target, so the CSF record names no single
 * target. The line is approved verbatim (#736 6087027524, Q1).
 */
const CSF_PLAYBOOK =
  "NIST CSF findings are measured against each subcategory's target level in the CSF Playbook.";
const ZT_DEFAULT =
  "Zero Trust findings are measured against target stage 3, SHIELD's default: no engagement target was set.";

function playbook(): RiskTargetUsed {
  return {
    kind: "csf",
    framework: null,
    target: null,
    source: "playbook",
    origin: "live_at_generate",
  };
}

describe("targetSentences, the CSF Playbook baseline (#474 D')", () => {
  it("states the Playbook line for CSF", () => {
    expect(targetSentences([playbook()], true)).toEqual([CSF_PLAYBOOK]);
  });

  it("keeps the Zero Trust line beside it, in the API's order", () => {
    const zt: RiskTargetUsed = {
      kind: "zt",
      framework: "cisa_ztmm_2_0",
      target: 3,
      source: "default",
      origin: "live_at_generate",
    };
    expect(targetSentences([playbook(), zt], true)).toEqual([
      CSF_PLAYBOOK,
      ZT_DEFAULT,
    ]);
  });
});
