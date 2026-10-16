import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ValueLoopCard, type ValueSummary } from "./ValueLoopCard";

/**
 * TD-5 (for #1060), #1299 folded in: the home card's Tech Debt savings say how
 * many of their costs are AI estimates, with the approved E6 sentence (#736
 * 6220094031 item 3). Strings typed here.
 */

/** A summary with everything pending and nothing unresolved. Overridden per test. */
function summary(over: Partial<ValueSummary> = {}): ValueSummary {
  return {
    tech_debt_savings_usd: null,
    tech_debt_savings_cost_known: true,
    tech_debt_savings_unresolved: false,
    zt_gap_count: null,
    zt_gap_unresolved: false,
    // No released ZT service, so there is no target to attribute. `null` for
    // both counts is what the API sends whenever the figure is null — see
    // `_TargetedKindTotal`. A fixture setting `0` here would assert "nothing
    // was assumed" about a figure that does not exist, and would put the test
    // suite in a state the server never produces.
    zt_services: 0,
    zt_targets_defaulted: null,
    zt_targets_unusable: null,
    // #209: null for the same reason the two above are null -- the figure
    // itself does not exist, so a 0 would assert "every figure matches your
    // reports" over something nobody measured.
    zt_targets_computed_live: null,
    attack_uncovered_count: null,
    attack_uncovered_unresolved: false,
    attack_uncovered_withheld: false,
    // Null exactly when the uncovered count is (#554).
    attack_not_verified_count: null,
    csf_gap_count: null,
    csf_gap_unresolved: false,
    csf_services: 0,
    csf_targets_defaulted: null,
    csf_targets_unusable: null,
    csf_targets_computed_live: null,
    has_any_data: false,
    has_unresolved: false,
    ...over,
  };
}

describe("the home card's savings and AI estimates (TD-5)", () => {
  it("names the estimated costs the savings include", () => {
    render(
      <ValueLoopCard
        summary={summary({
          tech_debt_savings_usd: 38000,
          tech_debt_savings_ai_estimate_count: 2,
          has_any_data: true,
        })}
      />,
    );
    expect(screen.getByText(/2 costs are AI estimates/)).toBeInTheDocument();
  });

  it("uses the singular for one", () => {
    render(
      <ValueLoopCard
        summary={summary({
          tech_debt_savings_usd: 38000,
          tech_debt_savings_ai_estimate_count: 1,
          has_any_data: true,
        })}
      />,
    );
    expect(screen.getByText(/1 cost is an AI estimate/)).toBeInTheDocument();
  });

  it("says nothing about estimates when none is included", () => {
    render(
      <ValueLoopCard
        summary={summary({
          tech_debt_savings_usd: 38000,
          tech_debt_savings_ai_estimate_count: 0,
          has_any_data: true,
        })}
      />,
    );
    // POSITIVE CONTROL: the savings hint itself rendered.
    expect(
      screen.getByText(/Annual spend on tools marked to cut/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/AI estimate/)).toBeNull();
  });
});
