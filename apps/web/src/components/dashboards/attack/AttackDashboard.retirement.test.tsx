import "@testing-library/jest-dom/vitest";

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type {
  AttackDashboardData,
  DashTechnique,
} from "@/lib/dashboards/attack";

import { AttackDashboard } from "./AttackDashboard";

/**
 * #686 (D-105) on the CLIENT dashboard: a tool the consolidation plan retires
 * is labelled "planned retirement", one the plan cannot answer for
 * "retirement status unknown", and the screen says the labels reflect the
 * CURRENT plan (the released PDF keeps the plan at finalize). Copy approved on
 * #686, written out here.
 */

function technique(code: string, tools: string[]): DashTechnique {
  return {
    code,
    name: `Technique ${code}`,
    tactic_name: "Execution",
    status: "covered",
    detection_tools: tools,
    prevention_tools: [],
    response_tools: [],
    rationale: null,
  };
}

function data(extra: Partial<AttackDashboardData> = {}): AttackDashboardData {
  return {
    service_id: "s1",
    service_title: "ATT&CK Coverage",
    released_at: "2026-09-01T12:00:00Z",
    deliverable_version: 1,
    rollup: {
      total_evaluated: 3,
      covered: 3,
      partial: 0,
      gap: 0,
      not_applicable: 0,
      coverage_pct: 100,
      coverage_measured: true,
      by_tactic: [],
    },
    techniques: [
      technique("T1190", ["Splunk Enterprise", "CrowdStrike Falcon"]),
      technique("T1059", ["Homegrown Script"]),
    ],
    ...extra,
  };
}

function row(code: string): HTMLElement {
  const tr = screen.getByText(code).closest("tr");
  if (!tr) throw new Error(`no table row for ${code}`);
  return tr;
}

const NOTES = [
  "1 of the 3 covered or partial techniques cites a tool marked for planned retirement; 0 rely on such tools alone.",
  "Retirement status could not be determined for 1 cited tool.",
];

describe("AttackDashboard, planned retirements (#686)", () => {
  it("labels each tool by the plan's state, and leaves a retained one bare", () => {
    render(
      <AttackDashboard
        data={data({
          tool_retirement: {
            "Splunk Enterprise": "planned_retirement",
            "Homegrown Script": "unknown",
          },
          retirement_notes: NOTES,
        })}
      />,
    );
    expect(
      within(row("T1190")).getByText(
        "Splunk Enterprise (planned retirement), CrowdStrike Falcon",
      ),
    ).toBeInTheDocument();
    expect(
      within(row("T1059")).getByText(
        "Homegrown Script (retirement status unknown)",
      ),
    ).toBeInTheDocument();
  });

  it("states the counts and that the labels reflect the current plan", () => {
    render(
      <AttackDashboard
        data={data({
          tool_retirement: { "Splunk Enterprise": "planned_retirement" },
          retirement_notes: NOTES,
        })}
      />,
    );
    for (const n of NOTES) expect(screen.getByText(n)).toBeInTheDocument();
    expect(
      screen.getByText(
        "Retirement labels reflect the current consolidation plan.",
      ),
    ).toBeInTheDocument();
  });

  it("says nothing about retirement when the client has no plan", () => {
    render(<AttackDashboard data={data()} />);
    // APPEAR before ABSENT: the row renders, so the absence is not vacuous.
    expect(
      within(row("T1190")).getByText("Splunk Enterprise, CrowdStrike Falcon"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/retirement/i)).toBeNull();
  });
});
