import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { AttackHeatmap } from "@/lib/attack/types";

import { AttackHeatmapCard } from "./AttackHeatmapCard";

function heatmap(over: Partial<AttackHeatmap> = {}): AttackHeatmap {
  return {
    assessment_id: "a1",
    version: 1,
    total_techniques: 193,
    total_sub_techniques: 440,
    scored_count: 10,
    unscored_count: 623,
    covered: 4,
    partial: 2,
    gap: 4,
    not_applicable: 0,
    coverage_pct: 50,
    by_tactic: [],
    ...over,
  };
}

describe("AttackHeatmapCard", () => {
  it("renders the pending-review count beside the coverage percentage", () => {
    // #102. `coverage_pct` is a ratio over the techniques that can currently be
    // CLAIMED, so withholding a row leaves BOTH sides of it and the percentage
    // stops being self-describing. The backend test of the same shape
    // (`test_narrowing_the_denominator_can_raise_the_ratio_and_that_is_stated`)
    // shows 95% becoming 100% when one partial is withheld. A bare percentage on
    // this card over withheld rows is the false assurance the whole rule exists
    // to prevent, so the count travels with it.
    render(<AttackHeatmapCard heatmap={heatmap({ pending_review: 3 })} />);
    expect(screen.getByTestId("attack-heatmap-pending")).toHaveTextContent(
      /3 pending review/,
    );
  });

  it("says nothing about pending review when nothing is withheld", () => {
    // A permanent "0 pending review" would train the eye to skip the line, which
    // is how the number stops being read on the run where it is not zero.
    render(<AttackHeatmapCard heatmap={heatmap({ pending_review: 0 })} />);
    // Positive assertion FIRST. `queryByTestId(...).toBeNull()` on its own passes
    // when the card renders nothing at all -- including when the pending block is
    // deleted outright, which is how this test passed a deliberate revert of the
    // feature it guards. CLAUDE.md: assert what must appear before what must not.
    expect(screen.getByText(/Coverage 50%/)).toBeInTheDocument();
    expect(screen.queryByTestId("attack-heatmap-pending")).toBeNull();
  });

  it("treats a heatmap with no pending field at all as nothing withheld", () => {
    // Additive + defaulted (C0): a payload written before #102 has no
    // `pending_review` key, and `undefined` must not render as "undefined
    // pending review".
    render(<AttackHeatmapCard heatmap={heatmap()} />);
    expect(screen.queryByTestId("attack-heatmap-pending")).toBeNull();
    expect(screen.getByText(/Coverage 50%/)).toBeInTheDocument();
  });
});
