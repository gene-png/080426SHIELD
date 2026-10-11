import { describe, expect, it } from "vitest";

import { type RiskTargetUsed, targetSentences } from "./baseline";

/**
 * #474 D' (advisor, #736 6087786886, item 4): the CSF Playbook's three states,
 * recorded as the CSF target's source token. For the two that measure nothing
 * the CSF line is REPLACED by the approved copy, verbatim.
 */
const LINES: Record<string, string> = {
  playbook:
    "NIST CSF findings are measured against each subcategory's target level in the CSF Playbook.",
  playbook_no_targets:
    "NIST CSF was not measured for this register: the CSF Playbook has no target levels set.",
  playbook_no_scores:
    "NIST CSF was not measured for this register: the CSF Playbook has no scores.",
};

function csf(source: string): RiskTargetUsed {
  return {
    kind: "csf",
    framework: null,
    target: null,
    source,
    origin: "live_at_generate",
  };
}

describe("targetSentences, the CSF Playbook states (#474 D')", () => {
  for (const [source, line] of Object.entries(LINES)) {
    it(`states ${source}`, () => {
      expect(targetSentences([csf(source)], true)).toEqual([line]);
    });
  }
});
