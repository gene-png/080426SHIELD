import "@testing-library/jest-dom/vitest";

import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { GapAnalysis, GapItem } from "@/lib/zt/types";

import { ZtGapList } from "./ZtGapList";

/**
 * Z4 (#736 6204461502 section 6, approved by Gene at 6205956728 with Q-B
 * "the order plus the working"): stages by name, the gap in words, and the
 * priority with its working, one decimal rounded down. Every literal below is
 * the approved text with the test's own values, never built from the
 * component.
 */

const CISA = [
  { stage: 1, label: "Traditional", description: "" },
  { stage: 2, label: "Initial", description: "" },
  { stage: 3, label: "Advanced", description: "" },
  { stage: 4, label: "Optimal", description: "" },
];

function gap(over: Partial<GapItem>): GapItem {
  return {
    code: "CISA.ID.01",
    pillar_code: "ID",
    pillar_name: "Identity",
    name: "Authentication",
    outcome: "o",
    current_stage: 1,
    target_stage: 4,
    gap_size: 3,
    priority_score: 3.6,
    pillar_weight: 1.2,
    notes: null,
    ...over,
  };
}

function render1(g: GapItem) {
  const analysis: GapAnalysis = {
    assessment_id: "a1",
    version: 1,
    framework: "cisa_ztmm_2_0",
    target_stage: g.target_stage,
    target_label: "Optimal",
    total_gap_count: 1,
    unscored_count: 0,
    gap_count_by_pillar: {},
    gaps: [g],
  };
  return render(
    <ZtGapList
      analysis={analysis}
      loading={false}
      targetStage={g.target_stage}
      onChangeTargetStage={() => {}}
      stages={CISA}
    />,
  );
}

function text(container: HTMLElement): string {
  return container.textContent ?? "";
}

describe("ZtGapList Z4: names, the gap in words, the priority with its working", () => {
  it("shows the approved example: Traditional → Optimal, 3 stages, Priority 3.6", () => {
    const { container } = render1(gap({}));
    const t = text(container);
    expect(t).toContain("Traditional → Optimal");
    expect(t).toContain("3 stages below target");
    expect(t).toContain(
      "Priority 3.6: 3 stages below target × 1.2 (Identity weighting)",
    );
    // The old forms are gone.
    expect(t).not.toMatch(/S1 → S4/);
    expect(t).not.toMatch(/gap 3/);
    expect(t).not.toMatch(/priority 3\.60/);
  });

  it("says 1 stage, singular", () => {
    const { container } = render1(
      gap({
        current_stage: 3,
        gap_size: 1,
        pillar_code: "DT",
        pillar_name: "Data",
        priority_score: 1.15,
        pillar_weight: 1.15,
      }),
    );
    const t = text(container);
    expect(t).toContain("Advanced → Optimal");
    // One decimal, rounded DOWN: 1.15 shows as 1.1, the weight as stored.
    expect(t).toContain(
      "Priority 1.1: 1 stage below target × 1.15 (Data weighting)",
    );
    expect(t).not.toContain("1 stages");
  });

  it("rounds down a priority whose float sits just under its decimal", () => {
    // 2 × 1.15 = 2.3, stored as 2.3; 2.3 * 10 is 22.999… in floating point.
    const { container } = render1(
      gap({
        current_stage: 2,
        gap_size: 2,
        pillar_code: "DT",
        pillar_name: "Data",
        priority_score: 2.3,
        pillar_weight: 1.15,
      }),
    );
    expect(text(container)).toContain(
      "Priority 2.3: 2 stages below target × 1.15 (Data weighting)",
    );
  });
});
