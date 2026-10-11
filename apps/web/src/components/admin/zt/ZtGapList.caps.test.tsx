import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { GapAnalysis } from "@/lib/zt/types";

import { ZtGapList } from "./ZtGapList";

/**
 * #839: the consultant's gap list states each DoD target cap, in the API's own
 * sentences (`GapAnalysisResponse.target_cap_notes`, from `zt/target_caps.py`,
 * the approved copy C1 and C2), rendered as given.
 */

const C2 =
  "3.5 Continuous Monitoring and Ongoing Authorizations has no DoD Target activities, so it moves from Below Target straight to Advanced.";

function analysis(notes: string[] | undefined): GapAnalysis {
  return {
    assessment_id: "a1",
    version: 1,
    framework: "dod_ztra",
    target_stage: 2,
    target_label: "Target",
    total_gap_count: 0,
    unscored_count: 0,
    gap_count_by_pillar: {},
    gaps: [],
    target_cap_notes: notes,
  };
}

const STAGES = [
  { stage: 1, label: "Below Target", description: "" },
  { stage: 2, label: "Target", description: "" },
  { stage: 3, label: "Advanced", description: "" },
];

describe("ZtGapList states the DoD target caps (#839)", () => {
  it("lists the API's sentences", () => {
    render(
      <ZtGapList
        analysis={analysis([C2])}
        loading={false}
        targetStage={2}
        onChangeTargetStage={() => {}}
        stages={STAGES}
      />,
    );
    expect(screen.getByTestId("zt-target-caps")).toHaveTextContent(C2);
  });

  it("shows nothing when nothing is capped", () => {
    render(
      <ZtGapList
        analysis={analysis([])}
        loading={false}
        targetStage={2}
        onChangeTargetStage={() => {}}
        stages={STAGES}
      />,
    );
    expect(screen.getByText(/0 gaps/)).toBeInTheDocument();
    expect(screen.queryByTestId("zt-target-caps")).toBeNull();
  });
});
