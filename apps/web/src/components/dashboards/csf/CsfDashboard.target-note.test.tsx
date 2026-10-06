import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { CsfDashboardData } from "@/lib/dashboards/csf";

import { CsfDashboard } from "./CsfDashboard";

/**
 * The CSF twin of #741, found by the twin sweep. The target card's sub-label
 * appends `renderedAgainstNote` (" These figures use your target as it stands
 * today. ...") straight after a lead-in with no full stop, so a live-read
 * dashboard read "Your target, chosen at intake These figures use ...".
 * Rendered, and pinned as whole strings so a missing stop between ANY two
 * sentences is red.
 */

const LIVE =
  " These figures use your target as it stands today. Your released report" +
  " was rendered against the target on file at the time, so the two can" +
  " differ.";

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

describe("CsfDashboard target note ends its lead-in with a period (#741 twin)", () => {
  it("a client-chosen target followed by the live-read sentence", () => {
    render(<CsfDashboard data={dashboard({ target_frozen_at: null })} />);
    expect(
      screen.getByText("Your target, chosen at intake." + LIVE),
    ).toBeVisible();
  });

  it("an assumed target followed by the live-read sentence", () => {
    render(
      <CsfDashboard
        data={dashboard({
          target_tier_source: "default",
          target_frozen_at: null,
        })}
      />,
    );
    expect(
      screen.getByText("Default target — no tier chosen at intake." + LIVE),
    ).toBeVisible();
  });

  it("a frozen client-chosen target is one sentence", () => {
    render(<CsfDashboard data={dashboard({})} />);
    expect(screen.getByText("Your target, chosen at intake.")).toBeVisible();
  });
});
