import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type {
  Redundancy,
  TechDebtDashboardData,
  TechDebtItem,
} from "@/lib/dashboards/techDebt";

import { TechDebtDashboard } from "./TechDebtDashboard";

// TD-5 (for #1060), #1299 folded in: a savings figure that includes an
// AI-estimated cost says so, with the approved E6 sentence (#736 6220094031
// item 3): the "Identified savings" card and each redundancy card. Strings
// typed here. The world is redundancyFloor.test.tsx's, with every cost known.

function tool(name: string, cost: number | null): TechDebtItem {
  return {
    name,
    vendor: null,
    category: "EDR",
    function: null,
    annual_cost_usd: cost,
    license_count: null,
    disposition: "cut",
    notes: null,
    bundle: null,
    ai_estimate: false,
  };
}

function data(r: Partial<Redundancy>): TechDebtDashboardData {
  const items = [
    tool("CrowdStrike Falcon", 120000),
    tool("Homegrown EDR", null),
  ];
  return {
    service_id: "11111111-1111-4111-8111-111111111111",
    service_title: "Tech Debt",
    released_at: "2026-10-08T00:00:00Z",
    deliverable_version: 1,
    ai_source: {
      state: "live",
      sentence: "AI suggestions in this assessment came from a live AI model.",
      live_runs: 1,
      fixture_runs: 0,
    },
    total_applications: 2,
    bundle_part_count: 0,
    annual_spend_usd: 120000,
    identified_savings_usd: 120000,
    savings_cost_known: false,
    spend_completeness: "partial",
    source_rows_total: 2,
    included_count: 2,
    excluded_count: 0,
    excluded_count_exact: true,
    redundant_category_count: 1,
    spend_by_category: [],
    sprawl_by_category: [],
    redundancies: [
      { category: "EDR", count: 2, savings_usd: 120000, items, ...r },
    ],
    items,
  } as unknown as TechDebtDashboardData;
}

function withEstimates(total: number, perCard: number): TechDebtDashboardData {
  const d = data({
    savings_cost_known: true,
    savings_ai_estimate_count: perCard,
  });
  return {
    ...d,
    savings_cost_known: true,
    savings_ai_estimate_count: total,
  } as TechDebtDashboardData;
}

describe("savings that include an AI estimate say so (TD-5)", () => {
  it("on the Identified savings card and the redundancy card", () => {
    render(<TechDebtDashboard data={withEstimates(2, 1)} />);
    expect(
      screen.getByText("From tools marked to cut · 2 costs are AI estimates"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("$120K/yr · 1 cost is an AI estimate"),
    ).toBeInTheDocument();
  });

  it("says nothing when no estimate is included", () => {
    render(<TechDebtDashboard data={withEstimates(0, 0)} />);
    // POSITIVE CONTROL: both savings lines rendered, without the sentence.
    expect(screen.getByText("From tools marked to cut")).toBeInTheDocument();
    expect(screen.getByText("$120K/yr")).toBeInTheDocument();
  });
});
