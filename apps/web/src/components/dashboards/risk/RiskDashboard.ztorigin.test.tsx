import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RiskDashboard } from "./RiskDashboard";
import type { RiskDashboardData } from "@/lib/dashboards/risk";

/**
 * #1343: the client's Risk dashboard states each ZT capability whose applied target has
 * no recorded origin, in the API's own lines (`risk/zt_target_origin.py`),
 * rendered as given. The sentence is approved verbatim at #736 comment
 * 6220094031 item 5, in the `{code}: ` form approved at 6225462107; quoted
 * here, never imported.
 */

const LINE =
  "CISA.ID.01: Who set this target is not recorded. An earlier AI run may have set it.";

function data(
  notes: string[],
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
    zt_unrecorded_target_notes: notes,
  };
}

describe("RiskDashboard states ZT targets whose origin is not recorded (#1343)", () => {
  it("renders the API's line", () => {
    render(<RiskDashboard data={data([LINE])} />);
    expect(screen.getByTestId("risk-zt-unrecorded-targets")).toHaveTextContent(
      LINE,
    );
  });

  it("renders nothing when every origin is recorded", () => {
    render(<RiskDashboard data={data([])} />);
    expect(screen.getByText("Open risks")).toBeInTheDocument();
    expect(screen.queryByTestId("risk-zt-unrecorded-targets")).toBeNull();
  });
});
