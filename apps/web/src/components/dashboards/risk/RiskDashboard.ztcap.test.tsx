import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RiskDashboard } from "./RiskDashboard";
import type { RiskDashboardData } from "@/lib/dashboards/risk";

/**
 * #915 (S3), approved verbatim at #736 comment 6049667540; the text below is
 * copied from the proposal in 6049167247. The client's Risk dashboard states
 * the DoD target cap in the API's own sentence, rendered as given.
 */

const SINGULAR =
  "In the DoD Zero Trust assessment, 1 capability has no DoD Advanced activities, so its target is Target (2): it is a finding only below Target. The Zero Trust deliverable names it.";

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
    zt_capped_target_note: note,
  };
}

describe("RiskDashboard states the DoD target cap (#915, S3)", () => {
  it("renders the API's sentence", () => {
    render(<RiskDashboard data={data(SINGULAR)} />);
    expect(screen.getByTestId("risk-zt-capped-target")).toHaveTextContent(
      SINGULAR,
    );
  });

  it("renders nothing when no target was capped", () => {
    render(<RiskDashboard data={data(null)} />);
    expect(screen.getByText("Open risks")).toBeInTheDocument();
    expect(screen.queryByTestId("risk-zt-capped-target")).toBeNull();
  });
});
