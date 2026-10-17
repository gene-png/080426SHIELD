import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { CsfDashboardData, CsfFunction } from "@/lib/dashboards/csf";

import { CsfDashboard } from "./CsfDashboard";

/**
 * #1183, the CSF half: the API sends the maturity percentage floored to one
 * decimal ((avg - 1) / (top - 1)), and the dashboard shows it as sent. It used
 * to go through `Math.round`, so the API's 66.6 read "67" on screen: the
 * dashboard disagreed with the API by rounding up what the API had floored.
 *
 * The figures are the API's own, for target tier 3 (66.6) and a current
 * average of 2.67 (55.6); the gap is their difference, 11.0. Every expected
 * string is typed here, never imported. Harness from
 * CsfDashboard.words.test.tsx.
 */

function dashboard(over: Partial<CsfDashboardData>): CsfDashboardData {
  return {
    ai_source: {
      state: "live",
      sentence: "AI suggestions in this assessment came from a live AI model.",
      live_runs: 1,
      fixture_runs: 0,
    },
    service_id: "11111111-1111-4111-8111-111111111111",
    service_title: "NIST CSF 2.0 Assessment",
    released_at: "2026-09-09T00:00:00Z",
    deliverable_version: 1,
    overall_label: "Risk Informed",
    current_tier: 2.67,
    current_pct: 55.6,
    coverage_pct: 100,
    target_tier: 3,
    target_label: "Repeatable",
    target_pct: 66.6,
    target_tier_source: "client",
    target_frozen_at: "2026-09-09T00:00:00Z",
    total_gap_count: 1,
    largest_gap_function: "Govern",
    largest_gap_pct: 11,
    functions: [],
    top_gaps: [],
    ...over,
  } as CsfDashboardData;
}

const govern: CsfFunction = {
  code: "GV",
  name: "Govern",
  current_tier: 2.67,
  current_label: "Risk Informed",
  current_pct: 55.6,
  target_pct: 66.6,
  gap_pct: 11,
  gap_count: 1,
  answered_count: 3,
  subcategory_count: 3,
  coverage_pct: 100,
  weakest: [],
};

describe("CsfDashboard, the maturity percentage as the API floored it (#1183)", () => {
  it("shows the overall current and target figures to one decimal, not rounded", () => {
    render(<CsfDashboard data={dashboard({})} />);
    expect(screen.getByText("Current maturity")).toBeVisible(); // positive first
    expect(screen.getByText("Risk Informed · 55.6")).toBeVisible();
    expect(screen.getByText("Repeatable · 66.6")).toBeVisible();
    expect(screen.queryByText("Repeatable · 67")).toBeNull();
    expect(screen.queryByText("Risk Informed · 56")).toBeNull();
  });

  it("shows the largest gap to one decimal", () => {
    render(<CsfDashboard data={dashboard({})} />);
    expect(screen.getByText("+11.0 points to target")).toBeVisible();
    expect(screen.queryByText("+11 points to target")).toBeNull();
  });

  it("shows a function's figures and its move to one decimal", () => {
    render(
      <CsfDashboard
        data={dashboard({
          functions: [govern],
        })}
      />,
    );
    expect(screen.getByText("Govern · Risk Informed · 55.6")).toBeVisible();
    expect(screen.getByText("66.6")).toBeVisible();
    expect(
      screen.getByText("1 gap · +11.0 pt move · 3/3 scored"),
    ).toBeVisible();
    expect(screen.queryByText("67")).toBeNull();
  });
});
