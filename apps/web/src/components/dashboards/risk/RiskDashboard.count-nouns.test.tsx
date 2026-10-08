import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RiskDashboard } from "./RiskDashboard";
import type { RiskDashboardData, RiskEntry } from "@/lib/dashboards/risk";

/**
 * #743: every count on the client's Risk screen agrees with its noun. The
 * report was "Of 1 entries"; the sweep was by shape (a count beside a noun),
 * so the pill and the banner's lead and remedy are pinned here too.
 *
 * Every fixture is a state a writer produces. The client reads a RELEASED
 * register (`routes/clients.py::risk_dashboard`), and `publish` refuses one
 * with an untiered entry (`risk_register_unrated_entries`), so every entry
 * here carries a tier. What CAN reach a released register is a null axis or a
 * null action: `generate` stores `None` when `_coerce_enum` cannot resolve
 * the value the model sent, and `publish` does not refuse either. The counts
 * are derived from the entries the way `risk_dashboard` derives them, so the
 * fixture cannot disagree with itself.
 */

// The remedy sentence Gene ruled (#854 F4); a swap is pending him (#736
// 6054419744), and this literal is the one line the swap edits.
const REMEDY = "Ask your consultant to complete those entries.";

function entry(
  title: string,
  over: Partial<Pick<RiskEntry, "axis" | "recommended_action">> = {},
): RiskEntry {
  return {
    title,
    axis: "detection",
    likelihood: "high",
    impact: "major",
    // `tier_for(high, major)` in `app/risk/engine.py`.
    tier: "high",
    recommended_action: "remediate",
    ...over,
  };
}

function tally(values: Array<string | null>): Record<string, number> {
  const out: Record<string, number> = {};
  for (const v of values) if (v !== null) out[v] = (out[v] ?? 0) + 1;
  return out;
}

function released(entries: RiskEntry[]): RiskDashboardData {
  const tiers = entries.map((e) => e.tier);
  const axes = entries.map((e) => e.axis);
  const actions = entries.map((e) => e.recommended_action);
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
    high_count: entries.length,
    tier_counts: tally(tiers),
    axis_counts: tally(axes),
    action_counts: tally(actions),
    // The occupied cell only; `matrixGrid` fills the other 24 at 0, and the
    // banner under test does not read the matrix.
    matrix: [
      {
        likelihood: "high",
        impact: "major",
        tier: "high",
        count: entries.length,
      },
    ],
    entries,
    entries_without_tier: tiers.filter((t) => t === null).length,
    entries_without_axis: axes.filter((a) => a === null).length,
    entries_without_action: actions.filter((a) => a === null).length,
  };
}

describe("RiskDashboard count nouns (#743)", () => {
  it("one entry missing from the axis breakdown, of one", () => {
    render(<RiskDashboard data={released([entry("Only", { axis: null })])} />);
    const note = screen.getByTestId("risk-entries-without-tier");
    const t = note.textContent ?? "";
    expect(t).toContain(
      "At least one entry is counted in Open risks and missing from a breakdown below.",
    );
    expect(t).toContain("Of 1 entry: 1 missing from the axis breakdown.");
    expect(t).toContain(REMEDY);
    expect(screen.getByText("1 entry")).toBeInTheDocument();
    expect(t).not.toContain("Some entries");
    expect(t).not.toContain("1 entries");
  });

  it("two missing from the axis breakdown and one from the action breakdown, of three", () => {
    render(
      <RiskDashboard
        data={released([
          entry("A", { axis: null }),
          entry("B", { axis: null }),
          entry("C", { recommended_action: null }),
        ])}
      />,
    );
    const t = screen.getByTestId("risk-entries-without-tier").textContent;
    expect(t).toContain(
      "At least one entry is counted in Open risks and missing from a breakdown below.",
    );
    expect(t).toContain(
      "Of 3 entries: 2 missing from the axis breakdown; 1 missing from the action breakdown.",
    );
    expect(t).toContain(REMEDY);
    expect(screen.getByText("3 entries")).toBeInTheDocument();
  });

  it("says nothing when every breakdown has every entry, and still counts them", () => {
    render(<RiskDashboard data={released([entry("A"), entry("B")])} />);
    expect(screen.getByText("2 entries")).toBeInTheDocument();
    expect(screen.queryByTestId("risk-entries-without-tier")).toBeNull();
  });

  it("offers the client a remedy it can take, not one only a consultant has", () => {
    render(<RiskDashboard data={released([entry("Only", { axis: null })])} />);
    const t = screen.getByTestId("risk-entries-without-tier").textContent;
    expect(t).toContain(REMEDY);
    expect(t).not.toMatch(/Regenerate/);
  });
});
