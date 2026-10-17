import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { TechDebtDashboardData } from "@/lib/dashboards/techDebt";

import { TechDebtDashboard } from "./TechDebtDashboard";

/**
 * #1427: the "Annual license spend" value carries the "≥" ON the figure when
 * the spend is a floor, as "Identified savings" does since #1094. Ruled on
 * #736 (6229792065). THREE values, mirroring the API's `spend_completeness`:
 * only "partial" is a floor. "unknown" (the upload was never reconciled) is
 * deliberately not worded as one -- the sub-line says "May not be complete" --
 * and "complete" is exact.
 */
function data(
  completeness: "complete" | "partial" | "unknown",
): TechDebtDashboardData {
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
    identified_savings_usd: 0,
    savings_cost_known: true,
    spend_completeness: completeness,
    source_rows_total: completeness === "unknown" ? null : 2,
    included_count: 2,
    excluded_count: 0,
    excluded_count_exact: true,
    no_cost_count: completeness === "partial" ? 1 : 0,
    redundant_category_count: 0,
    spend_by_category: [],
    sprawl_by_category: [],
    redundancies: [],
    items: [],
  } as unknown as TechDebtDashboardData;
}

function spendCard(): HTMLElement {
  return screen.getByText("Annual license spend", { exact: true })
    .parentElement as HTMLElement;
}

describe("the Annual license spend KPI marks a floor on the value (#1427)", () => {
  it("a partial spend reads '≥ $500,000'", () => {
    render(<TechDebtDashboard data={data("partial")} />);
    expect(spendCard()).toHaveTextContent("≥ $500,000");
  });

  it("a complete spend has no marker", () => {
    render(<TechDebtDashboard data={data("complete")} />);
    expect(spendCard()).toHaveTextContent("$500,000");
    expect(spendCard()).not.toHaveTextContent("≥");
  });

  it("an unreconciled spend is not worded as a floor", () => {
    render(<TechDebtDashboard data={data("unknown")} />);
    expect(spendCard()).toHaveTextContent("$500,000");
    expect(spendCard()).not.toHaveTextContent("≥");
    expect(spendCard()).toHaveTextContent("May not be complete");
  });
});
