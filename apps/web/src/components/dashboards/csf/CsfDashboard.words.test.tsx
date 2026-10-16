import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { CsfDashboardData } from "@/lib/dashboards/csf";

import { CsfDashboard } from "./CsfDashboard";

/**
 * C9 and W5 on the client's CSF dashboard, in the text Gene approved (#736
 * 6205956728, as written in 6204461502): the "Current maturity" figure is the
 * client's self-rating, and says so, and a gap's tiers read by name. Every
 * expected string is typed here, never imported. Harness from
 * CsfDashboard.target-note.test.tsx.
 */

function dashboard(over: Partial<CsfDashboardData>): CsfDashboardData {
  return {
    // #646 (Batch F): required since; not under test here.
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
    current_tier: 2,
    current_pct: 50,
    coverage_pct: 100,
    target_tier: 3,
    target_label: "Repeatable",
    target_pct: 75,
    target_tier_source: "client",
    target_frozen_at: "2026-09-09T00:00:00Z",
    total_gap_count: 0,
    largest_gap_function: null,
    largest_gap_pct: 0,
    functions: [],
    top_gaps: [],
    ...over,
  } as CsfDashboardData;
}

describe("CsfDashboard, self-rating copy (C9, W5)", () => {
  it("says the current maturity is self-reported, not validated", () => {
    render(<CsfDashboard data={dashboard({})} />);
    expect(screen.getByText("Current maturity")).toBeVisible(); // positive first
    expect(
      screen.getByText(
        "Averaged across all functions. Self-reported, not validated.",
      ),
    ).toBeVisible();
  });

  it("names a gap's tiers", () => {
    render(
      <CsfDashboard
        data={dashboard({
          total_gap_count: 1,
          top_gaps: [
            {
              code: "PR.AA-01",
              name: "Identity management",
              function: "PR",
              function_name: "Protect",
              current_tier: 2,
              target_tier: 3,
              gap_size: 1,
              priority_score: 1.15,
            },
          ],
        })}
      />,
    );
    expect(screen.getByText("Risk Informed → Repeatable")).toBeVisible();
    expect(screen.queryByText(/Tier 2 → 3/)).toBeNull();
  });
});
