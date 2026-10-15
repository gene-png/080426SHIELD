import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type {
  Redundancy,
  TechDebtDashboardData,
  TechDebtItem,
} from "@/lib/dashboards/techDebt";

import { TechDebtDashboard } from "./TechDebtDashboard";

// for #1044: a redundancy card's savings carry their own `savings_cost_known`.
// When a counted (cut) row in the category has no usable cost, the figure is
// a floor and the card marks it with "≥ ", the marker the admin plan card and
// the what-if already use for the same fact. A category whose flag is missing
// (an API older than the field) is NOT read as exact: missing data defaults to
// unconfirmed.

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

describe("a redundancy card marks floor savings (#1044)", () => {
  it("prints the exact figure when every counted cost is known", () => {
    render(<TechDebtDashboard data={data({ savings_cost_known: true })} />);
    expect(screen.getByText("$120K/yr")).toBeInTheDocument();
    expect(screen.queryByText("≥ $120K/yr")).toBeNull();
  });

  it("marks the figure as a floor when a counted cost is unknown", () => {
    render(<TechDebtDashboard data={data({ savings_cost_known: false })} />);
    expect(screen.getByText("≥ $120K/yr")).toBeInTheDocument();
    expect(screen.queryByText("$120K/yr")).toBeNull();
  });

  it("marks the figure as a floor when the flag is missing", () => {
    render(<TechDebtDashboard data={data({})} />);
    expect(screen.getByText("≥ $120K/yr")).toBeInTheDocument();
  });

  // Three values at a known amount of 0. "Unknown" must not collapse into
  // "nothing to save": the floor line shows at $0 unless the flag is exactly
  // true. (The API sends (0.0, false) for a category whose only counted row is
  // a Cut part.)
  it("shows a $0 floor when the amount is 0 and a counted cost is unknown", () => {
    render(
      <TechDebtDashboard
        data={data({ savings_usd: 0, savings_cost_known: false })}
      />,
    );
    expect(screen.getByText("≥ $0/yr")).toBeInTheDocument();
  });

  it("shows a $0 floor when the amount is 0 and the flag is missing", () => {
    render(<TechDebtDashboard data={data({ savings_usd: 0 })} />);
    expect(screen.getByText("≥ $0/yr")).toBeInTheDocument();
  });

  it("shows no savings line when the amount is 0 and every cost is known", () => {
    render(
      <TechDebtDashboard
        data={data({ savings_usd: 0, savings_cost_known: true })}
      />,
    );
    // The card itself is there (positive state first), with no savings line.
    expect(screen.getByText("· 2 licenses")).toBeInTheDocument();
    expect(screen.queryByText(/\/yr$/)).toBeNull();
  });
});
