import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type {
  Redundancy,
  TechDebtDashboardData,
  TechDebtItem,
} from "@/lib/dashboards/techDebt";

import { TechDebtDashboard } from "./TechDebtDashboard";

/**
 * #1094: the headline "Identified savings" value carries the "≥" ON the figure
 * when the savings are a floor, with the same marker the PDF, DOCX and plan card
 * use; the "Floor" sub-line stays. Ruled on #736 (6229200940). An exact figure
 * has no marker, and a flag that is MISSING is not read as exact (missing data
 * defaults to unconfirmed).
 */
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
    annual_spend_usd: 500000,
    identified_savings_usd: 777000,
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
      { category: "EDR", count: 2, savings_usd: 111000, items, ...r },
    ],
    items,
  } as unknown as TechDebtDashboardData;
}

function savingsValue(): HTMLElement {
  // The KPI card's label is the anchor; its value is the figure in its card.
  const label = screen.getByText("Identified savings");
  const card = label.parentElement as HTMLElement;
  return card;
}

describe("the Identified savings KPI marks a floor on the value (#1094)", () => {
  it("a floor reads '≥ $777,000' and keeps its Floor sub-line", () => {
    render(<TechDebtDashboard data={data({})} />);
    const card = savingsValue();
    expect(card).toHaveTextContent("≥ $777,000");
    expect(card).toHaveTextContent("Floor — some cut tools lacked a cost");
  });

  it("an exact figure has no marker", () => {
    const d = {
      ...data({}),
      savings_cost_known: true,
    } as TechDebtDashboardData;
    render(<TechDebtDashboard data={d} />);
    const card = savingsValue();
    expect(card).toHaveTextContent("$777,000");
    expect(card).not.toHaveTextContent("≥");
    expect(card).toHaveTextContent("From tools marked to cut");
  });

  it("a missing flag is a floor, not an exact figure", () => {
    const d = { ...data({}) } as Record<string, unknown>;
    delete d.savings_cost_known;
    render(<TechDebtDashboard data={d as unknown as TechDebtDashboardData} />);
    expect(savingsValue()).toHaveTextContent("≥ $777,000");
  });
});
