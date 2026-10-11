import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RiskDashboard } from "./RiskDashboard";
import type { RiskDashboardData } from "@/lib/dashboards/risk";

/**
 * Ruling #736 6104067136 (see #1033): the client's Risk dashboard states the
 * same three CSF Playbook results the files do. Where scores and targets
 * never shared a row (`csf_no_shared_row`, read by the files' reader), R11's
 * line; the true no-scores case and a register predating the field (absent)
 * keep the original line. Fixture copied from the csfsource suite.
 */

const NO_SCORES =
  "NIST CSF was not measured for this register: the CSF Playbook has no scores.";
const NO_SHARED_ROW =
  "NIST CSF was not measured for this register: no CSF Playbook row has both a score and a target.";
const MEASURED =
  "NIST CSF findings are measured against each subcategory's target level in the CSF Playbook.";

function data(
  source: string,
  csfNoSharedRow: boolean | undefined,
): RiskDashboardData {
  const entries: RiskDashboardData["entries"] = [];
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
    csf_source_note: null,
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
    ...(csfNoSharedRow === undefined
      ? {}
      : { csf_no_shared_row: csfNoSharedRow }),
  };
}

function lines(): string {
  return screen.getByTestId("risk-targets-used").textContent ?? "";
}

describe("RiskDashboard, the CSF Playbook's three results (#736 6104067136)", () => {
  it("no row with both a score and a target: R11's line", () => {
    render(<RiskDashboard data={data("playbook_no_scores", true)} />);
    expect(lines()).toContain(NO_SHARED_ROW);
    expect(lines()).not.toContain(NO_SCORES);
  });

  it("true no scores: the original line", () => {
    render(<RiskDashboard data={data("playbook_no_scores", false)} />);
    expect(lines()).toContain(NO_SCORES);
    expect(lines()).not.toContain(NO_SHARED_ROW);
  });

  it("a response predating the field: the original line", () => {
    render(<RiskDashboard data={data("playbook_no_scores", undefined)} />);
    expect(lines()).toContain(NO_SCORES);
    expect(lines()).not.toContain(NO_SHARED_ROW);
  });

  it("measured: the measured line, neither not-measured line", () => {
    render(<RiskDashboard data={data("playbook", false)} />);
    expect(lines()).toContain(MEASURED);
    expect(lines()).not.toContain(NO_SCORES);
    expect(lines()).not.toContain(NO_SHARED_ROW);
  });
});
