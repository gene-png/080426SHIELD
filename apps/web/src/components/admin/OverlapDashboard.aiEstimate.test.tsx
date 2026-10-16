import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { OverlapAnalysis } from "@/lib/tech_debt/types";

import { OverlapDashboard } from "./OverlapDashboard";

/**
 * TD-5 (for #1060): an AI-estimated cost is labelled wherever it appears
 * (copy E5, "AI estimate", approved on #736 6205600298), the admin "top cost"
 * list included. Typed here, never imported from the component.
 */

function analysis(aiEstimate: boolean): OverlapAnalysis {
  return {
    capability_list_id: "l1",
    capability_list_version: 1,
    by_category: [],
    by_vendor: [],
    top_cost_items: [
      {
        id: "a",
        name: "Tool A",
        vendor: null,
        category: null,
        annual_cost_usd: 12000,
        ai_estimate: aiEstimate,
      },
    ],
    total_cost: 12000,
    total_items: 1,
    uncategorized_count: 0,
    no_vendor_count: 0,
    no_cost_count: 0,
    total_cost_label: "Total annual cost",
  };
}

describe("OverlapDashboard's top costs and AI estimates (TD-5)", () => {
  it("labels an AI-estimated cost", () => {
    render(<OverlapDashboard analysis={analysis(true)} />);
    expect(screen.getByText("AI estimate")).toBeInTheDocument();
  });

  it("does not label a supplied cost", () => {
    render(<OverlapDashboard analysis={analysis(false)} />);
    // POSITIVE CONTROL: the row rendered.
    expect(screen.getByText("Tool A")).toBeInTheDocument();
    expect(screen.queryByText("AI estimate")).toBeNull();
  });
});
