import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { GapAnalysis, GapItem } from "@/lib/csf/types";

import { CsfGapList } from "./CsfGapList";

/**
 * W5 and W6 in the CSF self-rating gap list, in the text Gene approved (#736
 * 6205956728, as written in 6204461502): tiers by name, and the priority with
 * its working, one decimal rounded down, the weight as stored. Every expected
 * string is typed here, never imported. The examples are the package's own
 * ("Priority 1.1: 1 tier below target × 1.15 (Protect weighting)"), plus a
 * product a float gets wrong: 3 × 1.2 is 3.5999… in floating point, and the
 * priority is 3.6.
 */

function gap(over: Partial<GapItem>): GapItem {
  return {
    code: "PR.AA-01",
    function: "PR",
    function_name: "Protect",
    category: "PR.AA",
    name: "Identity management",
    outcome: "Identities are managed.",
    current_tier: 2,
    target_tier: 3,
    gap_size: 1,
    priority_score: 1.15,
    notes: null,
    weight: 1.15,
    ...over,
  };
}

function analysis(gaps: GapItem[]): GapAnalysis {
  return {
    assessment_id: "a-1",
    version: 1,
    target_tier: 3,
    target_label: "Repeatable",
    total_gap_count: gaps.length,
    unscored_count: 0,
    gap_count_by_function: {},
    gaps,
  };
}

describe("CsfGapList, tiers by name and the priority's working", () => {
  it("reads the package's example", () => {
    render(
      <CsfGapList
        analysis={analysis([gap({})])}
        targetTier={3}
        onChangeTargetTier={() => undefined}
      />,
    );
    expect(screen.getByText("Risk Informed → Repeatable")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Priority 1.1: 1 tier below target × 1.15 (Protect weighting)",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/T2 → T3|priority 1\.15/)).toBeNull();
  });

  it("rounds down in tenths, plural tiers, the weight as stored", () => {
    render(
      <CsfGapList
        analysis={analysis([
          gap({
            code: "DE.CM-01",
            function: "DE",
            function_name: "Detect",
            current_tier: 1,
            target_tier: 4,
            gap_size: 3,
            priority_score: 3.6,
            weight: 1.2,
          }),
        ])}
        targetTier={4}
        onChangeTargetTier={() => undefined}
      />,
    );
    expect(screen.getByText("Partial → Adaptive")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Priority 3.6: 3 tiers below target × 1.2 (Detect weighting)",
      ),
    ).toBeInTheDocument();
  });

  it("keeps a whole weight's decimal, as it is stored (1.0)", () => {
    render(
      <CsfGapList
        analysis={analysis([
          gap({
            code: "GV.OC-01",
            function: "GV",
            function_name: "Govern",
            current_tier: 1,
            target_tier: 3,
            gap_size: 2,
            priority_score: 2,
            weight: 1,
          }),
        ])}
        targetTier={3}
        onChangeTargetTier={() => undefined}
      />,
    );
    expect(
      screen.getByText(
        "Priority 2.0: 2 tiers below target × 1.0 (Govern weighting)",
      ),
    ).toBeInTheDocument();
  });
});
