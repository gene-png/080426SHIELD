import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ZtDashboardData, ZtPillar } from "@/lib/dashboards/zt";

import { ZtDashboard } from "./ZtDashboard";

/**
 * #700: the ZT client dashboard printed maturity percentages with no word on
 * how many capabilities they cover. The API returns `answered_count` per
 * pillar and the type carries it; nothing rendered it. A percentage over a
 * withheld population is not self-describing (`CLAUDE.md`), so the count of
 * scored and unscored capabilities sits beside the percentage, overall and per
 * pillar, as the CSF dashboard already does per function.
 *
 * Rendered, not computed: the assertions read the page.
 */

function pillar(over: Partial<ZtPillar>): ZtPillar {
  return {
    code: "identity",
    name: "Identity",
    capability_count: 10,
    answered_count: 10,
    current_pct: 40,
    current_label: "Initial",
    target_pct: 70,
    target_label: "Advanced",
    gap_pct: 30,
    weakest: [],
    ...over,
  };
}

function dashboard(pillars: ZtPillar[]): ZtDashboardData {
  return {
    // #646 (Batch F): required since; not under test here.
    ai_source: {
      state: "live",
      sentence: "AI suggestions in this assessment came from a live AI model.",
      live_runs: 1,
      fixture_runs: 0,
    },
    service_id: "11111111-1111-4111-8111-111111111111",
    unusable_target_codes: [],
    service_title: "Zero Trust Assessment",
    released_at: "2026-09-09T00:00:00Z",
    deliverable_version: 1,
    framework: "cisa_ztmm_2_0",
    framework_label: "CISA ZTMM 2.0",
    current_label: "Initial",
    current_pct: 40,
    target_label: "Advanced",
    target_pct: 70,
    target_stage: 3,
    target_stage_source: "client",
    target_frozen_at: "2026-09-09T00:00:00Z",
    engagement_target_capability_count: 4,
    total_gap_count: 3,
    largest_gap_pillar: "Identity",
    largest_gap_pct: 30,
    pillars,
  };
}

describe("ZtDashboard states how many capabilities its percentages cover (#700)", () => {
  it("says how many were scored and how many were not, beside the overall percentage", () => {
    render(
      <ZtDashboard
        data={dashboard([
          pillar({ code: "identity", name: "Identity", answered_count: 7 }),
          pillar({
            code: "devices",
            name: "Devices",
            capability_count: 8,
            answered_count: 8,
          }),
        ])}
      />,
    );
    expect(
      screen.getByText(
        "Weighted across all pillars · 15 of 18 capabilities scored; 3 not scored",
      ),
    ).toBeVisible();
  });

  it("says every capability was scored when every one was", () => {
    render(<ZtDashboard data={dashboard([pillar({})])} />);
    expect(
      screen.getByText(
        "Weighted across all pillars · all 10 capabilities scored",
      ),
    ).toBeVisible();
    expect(screen.queryByText(/not scored/)).not.toBeInTheDocument();
  });

  it("states each pillar's scored count beside its own percentage", () => {
    render(
      <ZtDashboard
        data={dashboard([
          pillar({ code: "identity", name: "Identity", answered_count: 7 }),
          pillar({
            code: "devices",
            name: "Devices",
            capability_count: 8,
            answered_count: 8,
            gap_pct: 10,
          }),
        ])}
      />,
    );
    expect(screen.getByText("+30 pt move · 7/10 scored")).toBeVisible();
    expect(screen.getByText("+10 pt move · 8/8 scored")).toBeVisible();
  });
});
