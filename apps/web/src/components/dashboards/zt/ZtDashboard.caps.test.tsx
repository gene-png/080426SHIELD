import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ZtDashboardData } from "@/lib/dashboards/zt";

import { ZtDashboard } from "./ZtDashboard";

/**
 * #839: the client's ZT dashboard states each DoD target cap, in the API's own
 * sentences (`zt/target_caps.py`, the approved copy C1), rendered as given and
 * never rebuilt here. The fixture is shaped like `ZtDashboardResponse`.
 */

const C1 =
  "1.1 User Inventory has no DoD Advanced activities, so its target is Target (2).";

function dashboard(notes: string[] | undefined): ZtDashboardData {
  return {
    ai_source: {
      state: "live",
      sentence: "AI suggestions in this assessment came from a live AI model.",
      live_runs: 1,
      fixture_runs: 0,
    },
    service_id: "11111111-1111-4111-8111-111111111111",
    unusable_target_codes: [],
    target_cap_notes: notes,
    service_title: "Zero Trust Assessment",
    released_at: "2026-09-09T00:00:00Z",
    deliverable_version: 1,
    framework: "dod_ztra",
    framework_label: "DoD ZTRA",
    current_label: "Target",
    current_pct: 40,
    target_label: "Advanced",
    target_pct: 70,
    target_stage: 3,
    target_stage_source: "client",
    target_frozen_at: "2026-09-09T00:00:00Z",
    engagement_target_capability_count: 4,
    total_gap_count: 1,
    largest_gap_pillar: "User",
    largest_gap_pct: 30,
    pillars: [
      {
        code: "USR",
        name: "User",
        capability_count: 4,
        answered_count: 4,
        current_pct: 40,
        current_label: "Target",
        target_pct: 70,
        target_label: "Advanced",
        gap_pct: 30,
        weakest: [],
      },
    ],
  } as ZtDashboardData;
}

describe("ZtDashboard states the DoD target caps (#839)", () => {
  it("lists the API's sentences", () => {
    render(<ZtDashboard data={dashboard([C1])} />);
    expect(screen.getByTestId("zt-target-caps")).toHaveTextContent(C1);
  });

  it("shows nothing when nothing is capped", () => {
    render(<ZtDashboard data={dashboard([])} />);
    expect(screen.getByText("Target maturity")).toBeInTheDocument();
    expect(screen.queryByTestId("zt-target-caps")).toBeNull();
  });
});
