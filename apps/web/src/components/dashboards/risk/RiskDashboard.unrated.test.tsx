import "@testing-library/jest-dom/vitest";

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RiskDashboard } from "./RiskDashboard";
import type { RiskDashboardData } from "@/lib/dashboards/risk";

/**
 * #844, the client's screen: an unrated entry reads "Not rated", the same
 * words the exported register prints, rather than a dash in three columns.
 */
function data(entries: RiskDashboardData["entries"]): RiskDashboardData {
  return {
    ai_source: {
      state: "live",
      sentence: "AI suggestions in this assessment came from a live AI model.",
      live_runs: 1,
      fixture_runs: 0,
    },
    client_id: "00000000-0000-0000-0000-0000000000aa",
    released_at: "2026-10-04T00:00:00Z",
    version: 1,
    total_entries: entries.length,
    critical_count: 0,
    high_count: 0,
    tier_counts: { low: 1 },
    axis_counts: { detection: 2 },
    action_counts: { remediate: 2 },
    matrix: [],
    entries,
    entries_without_tier: entries.filter((e) => e.tier === null).length,
    entries_without_axis: 0,
    entries_without_action: 0,
  };
}

function rowFor(title: string): HTMLElement {
  const row = screen.getByText(title).closest("tr");
  if (row === null) throw new Error(`no table row for ${title}`);
  return row;
}

describe("RiskDashboard unrated entries (#844)", () => {
  it("prints Not rated in the likelihood, impact and tier cells", () => {
    render(
      <RiskDashboard
        data={data([
          {
            title: "Unrated risk",
            axis: "detection",
            likelihood: null,
            impact: null,
            tier: null,
            recommended_action: "remediate",
          },
          {
            title: "Rated risk",
            axis: "detection",
            likelihood: "low",
            impact: "moderate",
            tier: "low",
            recommended_action: "remediate",
          },
        ])}
      />,
    );
    const unrated = within(rowFor("Unrated risk"));
    expect(unrated.getAllByText("Not rated")).toHaveLength(3);
    expect(within(rowFor("Rated risk")).queryByText("Not rated")).toBeNull();
  });
});
