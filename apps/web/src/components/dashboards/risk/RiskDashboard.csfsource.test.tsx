import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RiskDashboard } from "./RiskDashboard";
import type { RiskDashboardData } from "@/lib/dashboards/risk";

/**
 * #474 D': the client's Risk dashboard states where the register's CSF risks
 * come from, in the API's own sentence (`csf_source_note`), rendered as given.
 * Gene's note, approved verbatim at #736 comment 5984256202.
 */

const NOTE =
  "CSF risks in this register come from Kentro's evidence-based assessment. They can differ from your self-assessment on the CSF dashboard.";

function data(
  note: string | null,
  entries: RiskDashboardData["entries"] = [],
): RiskDashboardData {
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
    csf_source_note: note,
  };
}

describe("RiskDashboard states the CSF source (#474 D')", () => {
  it("renders the API's sentence", () => {
    render(<RiskDashboard data={data(NOTE)} />);
    expect(screen.getByTestId("risk-csf-source")).toHaveTextContent(NOTE);
  });

  it("renders nothing when the register has no CSF findings", () => {
    render(<RiskDashboard data={data(null)} />);
    expect(screen.getByText("Open risks")).toBeInTheDocument();
    expect(screen.queryByTestId("risk-csf-source")).toBeNull();
  });
});
