import "@testing-library/jest-dom/vitest";

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RiskDashboard } from "./RiskDashboard";
import type { RiskDashboardData } from "@/lib/dashboards/risk";

/**
 * Ruling #736 6105137014 (finding 2, option (i)): the client's dashboard says
 * nothing about dropped other axes. The kept axes are accurate as far as they
 * go, and a parse failure is not a client fact. The API does not send the
 * field to this screen; even a payload carrying it renders no note.
 * Fixtures copied from the other-axes suite.
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
    tier_counts: { low: entries.length },
    axis_counts: { detection: entries.length },
    action_counts: { remediate: entries.length },
    matrix: [],
    entries,
    entries_without_tier: 0,
    entries_without_axis: 0,
    entries_without_action: 0,
  };
}

function entry(
  title: string,
  other_axes: string[] | null,
): RiskDashboardData["entries"][number] {
  return {
    title,
    axis: "detection",
    other_axes,
    likelihood: "low",
    impact: "minor",
    tier: "low",
    recommended_action: "remediate",
  };
}

function cellUnder(header: string, title: string): string {
  const row = screen.getByText(title).closest("tr");
  if (row === null) throw new Error(`no table row for ${title}`);
  const table = row.closest("table");
  if (table === null) throw new Error(`no table for ${title}`);
  const headers = within(table)
    .getAllByRole("columnheader")
    .map((h) => h.textContent);
  const at = headers.indexOf(header);
  if (at === -1)
    throw new Error(`no "${header}" column among ${headers.join(" | ")}`);
  return row.querySelectorAll("td")[at]?.textContent ?? "";
}

describe("RiskDashboard, dropped other axes (#736 6105137014)", () => {
  it("renders the kept axes and no drop note", () => {
    const dropped = {
      ...entry("Partly dropped", ["prevention"]),
      other_axes_dropped: { invalid: 2 },
    } as RiskDashboardData["entries"][number];
    render(<RiskDashboard data={data([dropped])} />);
    // Positive first: the kept axis renders.
    expect(cellUnder("Other axes", "Partly dropped")).toBe("Prevention");
    expect(screen.queryByText(/could not be read/)).toBeNull();
    expect(screen.queryByTestId("risk-other-axes-dropped")).toBeNull();
  });
});
