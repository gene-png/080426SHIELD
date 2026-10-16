import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ZtDashboardData } from "@/lib/dashboards/zt";

import { ZtDashboard } from "./ZtDashboard";

/**
 * #1183: the API floors each maturity percentage to one decimal, so 2/3 of the
 * way up the scale is 66.6. The dashboard prints that figure as given, to one
 * decimal: rounding it again here printed "67", a number the API never sent and
 * the deliverable does not show. The fixture is shaped like
 * `ZtDashboardResponse`.
 */

function dashboard(): ZtDashboardData {
  return {
    ai_source: {
      state: "live",
      sentence: "AI suggestions in this assessment came from a live AI model.",
      live_runs: 1,
      fixture_runs: 0,
    },
    service_id: "11111111-1111-4111-8111-111111111111",
    unusable_target_codes: [],
    target_cap_notes: [],
    service_title: "Zero Trust Assessment",
    released_at: "2026-09-09T00:00:00Z",
    deliverable_version: 1,
    framework: "cisa_ztmm_2_0",
    framework_label: "CISA ZTMM 2.0",
    current_label: "Advanced",
    current_pct: 66.6,
    target_label: "Optimal",
    target_pct: 100,
    target_stage: 4,
    target_stage_source: "client",
    target_frozen_at: "2026-09-09T00:00:00Z",
    engagement_target_capability_count: 7,
    total_gap_count: 7,
    largest_gap_pillar: "Identity",
    largest_gap_pct: 33.4,
    pillars: [
      {
        code: "ID",
        name: "Identity",
        capability_count: 7,
        answered_count: 7,
        current_pct: 55.5,
        current_label: "Initial",
        target_pct: 100,
        target_label: "Optimal",
        gap_pct: 44.5,
        weakest: [],
      },
    ],
  } as ZtDashboardData;
}

describe("ZtDashboard prints the API's one-decimal percentages (#1183)", () => {
  it("prints the overall and target figures to one decimal", () => {
    render(<ZtDashboard data={dashboard()} />);
    expect(screen.getByText("Advanced · 66.6")).toBeVisible();
    // The overall target card and the pillar bar both print it.
    expect(screen.getAllByText("Optimal · 100.0")).toHaveLength(2);
    expect(screen.queryByText("Advanced · 67")).toBeNull();
  });

  it("prints each pillar's figures and gap to one decimal", () => {
    render(<ZtDashboard data={dashboard()} />);
    expect(screen.getByText("Initial · 55.5")).toBeVisible();
    expect(screen.getByText("+44.5 pt move · 7/7 scored")).toBeVisible();
    expect(screen.queryByText("Initial · 56")).toBeNull();
  });

  it("prints the largest gap to one decimal", () => {
    render(<ZtDashboard data={dashboard()} />);
    expect(screen.getByText("Largest: Identity · +33.4 points")).toBeVisible();
  });
});
