import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { GapAnalysis } from "@/lib/zt/types";

import { ZtGapList } from "./ZtGapList";

/**
 * #839 S1 (approved verbatim, #736 comment 6049667540): a stage stored above
 * its capability's maximum is disclosed on the consultant's gap list, beside
 * the C1 cap notes, in the API's own sentence (`stage_above_max_notes`),
 * rendered as given. The text is the example in 6049167247.
 */

const S1 =
  "1.1 User Inventory is recorded at stage 3, but it has no DoD Advanced activities, so every figure here counts it as Target (2).";

function analysis(notes: string[] | undefined): GapAnalysis {
  return {
    assessment_id: "a1",
    version: 1,
    framework: "dod_ztra",
    target_stage: 3,
    target_label: "Advanced",
    total_gap_count: 0,
    unscored_count: 0,
    gap_count_by_pillar: {},
    gaps: [],
    target_cap_notes: [],
    stage_above_max_notes: notes,
  };
}

const STAGES = [
  { stage: 1, label: "Below Target", description: "" },
  { stage: 2, label: "Target", description: "" },
  { stage: 3, label: "Advanced", description: "" },
];

function renderList(notes: string[] | undefined) {
  return render(
    <ZtGapList
      analysis={analysis(notes)}
      loading={false}
      targetStage={3}
      onChangeTargetStage={() => {}}
      stages={STAGES}
    />,
  );
}

describe("ZtGapList states a stored stage above its maximum (#839 S1)", () => {
  it("lists the API's sentence", () => {
    renderList([S1]);
    expect(screen.getByTestId("zt-stage-above-max")).toHaveTextContent(S1);
  });

  it("shows nothing when every stage is reachable", () => {
    renderList([]);
    expect(screen.getByText(/0 gaps/)).toBeInTheDocument();
    expect(screen.queryByTestId("zt-stage-above-max")).toBeNull();
  });
});
