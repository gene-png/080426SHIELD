import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RiskDashboard } from "./RiskDashboard";
import type { RiskDashboardData } from "@/lib/dashboards/risk";

/**
 * #474 D' (advisor, #736 6087786886, item 4): the client's Risk dashboard
 * states the CSF Playbook's state in its target lines; for a Playbook with no
 * targets or no scores the CSF line is REPLACED by the approved copy.
 */

const LINES: Record<string, string> = {
  playbook:
    "NIST CSF findings are measured against each subcategory's target level in the CSF Playbook.",
  playbook_no_targets:
    "NIST CSF was not measured for this register: the CSF Playbook has no target levels set.",
  playbook_no_scores:
    "NIST CSF was not measured for this register: the CSF Playbook has no scores.",
};

function data(
  source: string,
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
    targets: [
      {
        kind: "csf",
        framework: null,
        target: null,
        source,
        origin: "live_at_generate",
      },
    ],
    targets_recorded: true,
  };
}

describe("RiskDashboard states the CSF Playbook state (#474 D')", () => {
  for (const [source, line] of Object.entries(LINES)) {
    it(`renders ${source}, and no other Playbook line`, () => {
      render(<RiskDashboard data={data(source)} />);
      const box = screen.getByTestId("risk-targets-used");
      expect(box).toHaveTextContent(line);
      for (const [other, otherLine] of Object.entries(LINES)) {
        if (other !== source) expect(box).not.toHaveTextContent(otherLine);
      }
    });
  }
});
