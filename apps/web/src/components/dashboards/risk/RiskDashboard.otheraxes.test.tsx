import "@testing-library/jest-dom/vitest";

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RiskDashboard } from "./RiskDashboard";
import type { RiskDashboardData } from "@/lib/dashboards/risk";

/**
 * #736 6094620397, Risk E item 4, on the client's screen: a column headed
 * "Other axes"; comma-joined display names; an empty cell for `[]`; "Not
 * recorded" for NULL. Expected strings written out from the ruling.
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

describe("RiskDashboard other axes (#474 E item 4)", () => {
  it("renders each of the three states under an Other axes heading", () => {
    render(
      <RiskDashboard
        data={data([
          entry("Listed risk", ["prevention", "response"]),
          entry("Empty risk", []),
          entry("Unrecorded risk", null),
        ])}
      />,
    );
    // What must appear first: the heading and a populated cell.
    expect(
      screen.getByRole("columnheader", { name: "Other axes" }),
    ).toBeInTheDocument();
    expect(cellUnder("Other axes", "Listed risk")).toBe("Prevention, Response");
    expect(cellUnder("Other axes", "Empty risk")).toBe("");
    expect(cellUnder("Other axes", "Unrecorded risk")).toBe("Not recorded");
  });
});
