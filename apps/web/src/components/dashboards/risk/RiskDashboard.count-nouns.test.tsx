import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RiskDashboard } from "./RiskDashboard";
import type { RiskDashboardData, RiskEntry } from "@/lib/dashboards/risk";

/**
 * #743: every count on the client's Risk screen agrees with its noun. The
 * report was "Of 1 entries"; the sweep was by shape (a count beside a noun),
 * so the pill and the remedy sentence are pinned here too.
 */
function entry(title: string): RiskEntry {
  return {
    title,
    axis: "detection",
    likelihood: null,
    impact: null,
    tier: null,
    recommended_action: "remediate",
  };
}

function data(entries: RiskEntry[]): RiskDashboardData {
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
    tier_counts: {},
    axis_counts: { detection: entries.length },
    action_counts: { remediate: entries.length },
    matrix: [],
    entries,
    entries_without_tier: entries.length,
    entries_without_axis: 0,
    entries_without_action: 0,
  };
}

describe("RiskDashboard count nouns (#743)", () => {
  it("says 'Of 1 entry' and '1 entry' for a one-entry register", () => {
    render(<RiskDashboard data={data([entry("Only")])} />);
    const note = screen.getByTestId("risk-entries-without-tier");
    expect(note.textContent).toContain("Of 1 entry:");
    expect(note.textContent).not.toContain("1 entries");
    expect(screen.getByText("1 entry")).toBeInTheDocument();
  });

  it("says 'Of 2 entries' and '2 entries' for two", () => {
    render(<RiskDashboard data={data([entry("A"), entry("B")])} />);
    const note = screen.getByTestId("risk-entries-without-tier");
    expect(note.textContent).toContain("Of 2 entries:");
    expect(screen.getByText("2 entries")).toBeInTheDocument();
  });

  it("offers the client a remedy it can take, not one only a consultant has", () => {
    render(<RiskDashboard data={data([entry("Only")])} />);
    const note = screen.getByTestId("risk-entries-without-tier");
    expect(note.textContent).not.toMatch(/Regenerate/);
    expect(note.textContent).toContain(
      "Ask your consultant to complete those entries.",
    );
  });
});
