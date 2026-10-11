/**
 * The client's Functional redundancies card (for #835). `r.count` counts
 * LICENSES: a bundle split into named parts is one license however many of
 * its parts sit in the category. Copy approved by the advisor on #736
 * (comment 6056012075): "· {n} licenses", singular "· 1 license".
 */
import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type {
  TechDebtDashboardData,
  TechDebtItem,
} from "@/lib/dashboards/techDebt";

import { TechDebtDashboard, redundancyLicenses } from "./TechDebtDashboard";

function tool(name: string, cost: number | null): TechDebtItem {
  return {
    name,
    vendor: null,
    category: "EDR",
    function: null,
    annual_cost_usd: cost,
    license_count: null,
    disposition: "keep",
    notes: null,
  };
}

// CrowdStrike beside TWO parts of one split bundle: three rows, two licenses,
// which is what the API sends as `count`.
const EDR_ROWS = [
  tool("CrowdStrike Falcon", 120000),
  tool("Microsoft Defender for Endpoint", null),
  tool("Microsoft Defender for Cloud Apps", null),
];

function data(): TechDebtDashboardData {
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
    bundle_part_count: 2,
    annual_spend_usd: 414120,
    identified_savings_usd: 0,
    savings_cost_known: true,
    spend_completeness: "complete",
    source_rows_total: 2,
    included_count: 2,
    excluded_count: 0,
    excluded_count_exact: true,
    redundant_category_count: 1,
    spend_by_category: [],
    sprawl_by_category: [],
    redundancies: [
      { category: "EDR", count: 2, savings_usd: 0, items: EDR_ROWS },
    ],
    items: EDR_ROWS,
  } as unknown as TechDebtDashboardData;
}

describe("RedundancyCard license count", () => {
  it("counts a split bundle's two parts as one license", () => {
    render(<TechDebtDashboard data={data()} />);
    expect(screen.getByText("· 2 licenses")).toBeInTheDocument();
    expect(screen.queryByText(/· 3 /)).toBeNull();
    expect(screen.queryByText(/tools$/, { selector: "span" })).toBeNull();
  });

  it("uses the singular for one license", () => {
    expect(redundancyLicenses(1)).toBe("· 1 license");
    expect(redundancyLicenses(2)).toBe("· 2 licenses");
  });
});
