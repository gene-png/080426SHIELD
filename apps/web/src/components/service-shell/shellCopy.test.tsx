import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ProgressStages } from "@/components/admin/ProgressStages";

import { STAGE_LABELS, stageLabel, type FrameKind } from "./shellCopy";

/**
 * `STAGE_LABELS` is a copy of `ProgressStages`' private labels. The expected
 * words come from RENDERING ProgressStages, not from this module, so a change
 * on either side turns this red.
 */
function shown(key: string, kind: FrameKind): string {
  const { unmount } = render(
    <ProgressStages stages={[{ key, state: "current" }]} kind={kind} />,
  );
  const text = screen.getByTestId("progress-stages").textContent ?? "";
  unmount();
  return text.replace(/:.*$/, "");
}

describe("stage labels agree with ProgressStages", () => {
  const kinds: FrameKind[] = [
    "tech_debt",
    "attack_coverage",
    "nist_csf",
    "zero_trust_cisa",
    "zero_trust_dod",
  ];
  for (const key of Object.keys(STAGE_LABELS))
    for (const kind of kinds)
      it(`${key} for ${kind}`, () => {
        expect(stageLabel(key, kind)).toBe(shown(key, kind));
      });

  it("refuses a stage key it has no word for", () => {
    expect(() => stageLabel("ship", "tech_debt")).toThrow(/unknown stage/);
  });
});
