import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ConsolidationPlanSummary } from "@/lib/tech_debt/types";

import { ConsolidationPlanCard } from "./ConsolidationPlanCard";

/**
 * #1299 (TD-5), no admin exemption (#736 issuecomment-6225076633): the plan
 * card's "Estimated annual savings" says how many AI-estimated costs it
 * includes (copy E6, spelled out here, not imported), after its own hint.
 */
function summary(k: number): ConsolidationPlanSummary {
  return {
    capability_list_id: "list-1",
    capability_list_version: 1,
    total_items: 3,
    keep_count: 1,
    consolidate_count: 0,
    cut_count: 2,
    undecided_count: 0,
    estimated_annual_savings: 492000,
    savings_cost_known: true,
    savings_ai_estimate_count: k,
  };
}

const HINT =
  "Sum of the annual costs of rows marked Cut or Cut, covered by another tool.";

describe("ConsolidationPlanCard and AI estimates (#1299)", () => {
  it("states the estimates after the savings hint", () => {
    render(<ConsolidationPlanCard summary={summary(2)} />);
    expect(screen.getByText("$492,000")).toBeInTheDocument();
    expect(
      screen.getByText(`${HINT} · 2 costs are AI estimates`),
    ).toBeInTheDocument();
  });

  it("keeps the hint alone when the savings include no estimate", () => {
    render(<ConsolidationPlanCard summary={summary(0)} />);
    expect(screen.getByText(HINT)).toBeInTheDocument();
    expect(screen.queryByText(/AI estimate/)).toBeNull();
  });
});
