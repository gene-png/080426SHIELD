import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ValueLoopCard, type ValueSummary } from "./ValueLoopCard";

/**
 * #1427: the home card marks a savings floor with "≥" on the value, the glyph
 * every other surface uses for "at least" (#1094), not a trailing "+". Ruled on
 * #736 (6229792065). An exact figure has no marker.
 */
function summary(over: Partial<ValueSummary>): ValueSummary {
  return {
    tech_debt_savings_usd: 12345,
    tech_debt_savings_cost_known: true,
    tech_debt_savings_unresolved: false,
    zt_gap_count: null,
    zt_gap_unresolved: false,
    zt_services: 0,
    zt_targets_defaulted: null,
    zt_targets_unusable: null,
    zt_targets_computed_live: null,
    attack_uncovered_count: null,
    attack_uncovered_unresolved: false,
    attack_uncovered_withheld: false,
    attack_not_verified_count: null,
    csf_gap_count: null,
    csf_gap_unresolved: false,
    csf_services: 0,
    csf_targets_defaulted: null,
    csf_targets_unusable: null,
    csf_targets_computed_live: null,
    has_any_data: true,
    has_unresolved: false,
    ...over,
  };
}

describe("the home card's savings floor (#1427)", () => {
  it("a floor reads '≥ $12,345 / yr'", () => {
    render(
      <ValueLoopCard
        summary={summary({ tech_debt_savings_cost_known: false })}
      />,
    );
    expect(screen.getByText("≥ $12,345 / yr")).toBeInTheDocument();
    expect(screen.queryByText(/\+ \/ yr/)).toBeNull();
  });

  it("an exact figure reads '$12,345 / yr'", () => {
    render(<ValueLoopCard summary={summary({})} />);
    expect(screen.getByText("$12,345 / yr")).toBeInTheDocument();
  });
});
