import "@testing-library/jest-dom/vitest";

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type {
  AttackDashboardData,
  DashTechnique,
} from "@/lib/dashboards/attack";

import { AttackDashboard } from "./AttackDashboard";

/**
 * #889 on the CLIENT dashboard: a tool that is not in the client's CURRENT
 * security tool list is marked, the deliverable's sentence states how many
 * rows credit one, and the screen says the check reflects the current list.
 * "Not checked" is said too (Q1). Copy C1, C2, C3 and C5 approved verbatim
 * (#736 6090360421), written out here, never imported.
 */

const C1 =
  "1 technique row credits a tool that is not in the client's security tool list, so its status may count a tool the client does not use.";
const C2 =
  "Security tool list checks reflect the client's current security tool list.";
const C3 = " (not in the security tool list)";
const C5 =
  "The tools cited here were not checked against a security tool list, because the client has none.";

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
    ai_source: {
      state: "live",
      sentence: "AI suggestions in this assessment came from a live AI model.",
      live_runs: 1,
      fixture_runs: 0,
    },
    service_id: "s1",
    service_title: "ATT&CK Coverage",
    released_at: "2026-09-01T12:00:00Z",
    deliverable_version: 1,
    rollup: {
      total_evaluated: 2,
      covered: 2,
      partial: 0,
      gap: 0,
      not_applicable: 0,
      coverage_pct: 100,
      coverage_measured: true,
      by_tactic: [],
    },
    techniques: [
      technique("T1190", ["Splunk Enterprise", "Legacy AV"]),
      technique("T1059", ["CrowdStrike Falcon"]),
    ],
    ...extra,
  };
}

function row(code: string): HTMLElement {
  const tr = screen.getByText(code).closest("tr");
  if (!tr) throw new Error(`no table row for ${code}`);
  return tr;
}

describe("AttackDashboard, tools outside the security tool list (#889)", () => {
  it("marks the tool, states the rows, and says the check is current", () => {
    render(
      <AttackDashboard
        data={data({ tool_outside_subset: ["Legacy AV"], subset_notes: [C1] })}
      />,
    );
    expect(
      within(row("T1190")).getByText(`Splunk Enterprise, Legacy AV${C3}`),
    ).toBeInTheDocument();
    expect(
      within(row("T1059")).getByText("CrowdStrike Falcon"),
    ).toBeInTheDocument();
    expect(screen.getByText(C1)).toBeInTheDocument();
    expect(screen.getByText(C2)).toBeInTheDocument();
  });

  it("stacks the mark after the retirement mark", () => {
    render(
      <AttackDashboard
        data={data({
          tool_retirement: { "Legacy AV": "planned_retirement" },
          retirement_notes: [],
          tool_outside_subset: ["Legacy AV"],
          subset_notes: [C1],
        })}
      />,
    );
    expect(
      within(row("T1190")).getByText(
        `Splunk Enterprise, Legacy AV (planned retirement)${C3}`,
      ),
    ).toBeInTheDocument();
  });

  it("says not checked when the client has no list, and marks nothing", () => {
    render(<AttackDashboard data={data({ subset_notes: [C5] })} />);
    expect(screen.getByText(C5)).toBeInTheDocument();
    expect(
      within(row("T1190")).getByText("Splunk Enterprise, Legacy AV"),
    ).toBeInTheDocument();
    expect(screen.queryByText(C2)).toBeNull();
  });

  it("says nothing when the check ran and found nothing", () => {
    render(
      <AttackDashboard
        data={data({ tool_outside_subset: [], subset_notes: [] })}
      />,
    );
    // APPEAR before ABSENT: the row renders, so the absence is not vacuous.
    expect(
      within(row("T1190")).getByText("Splunk Enterprise, Legacy AV"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/security tool list/)).toBeNull();
  });
});
