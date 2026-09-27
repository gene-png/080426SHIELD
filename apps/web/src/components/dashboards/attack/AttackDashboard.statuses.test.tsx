import "@testing-library/jest-dom/vitest";

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type {
  AttackDashboardData,
  DashTechnique,
} from "@/lib/dashboards/attack";

import { AttackDashboard } from "./AttackDashboard";

/**
 * #554 on the CLIENT dashboard. Two things the owner forbade:
 *   * an unverified technique shown as "N/A" -- the chip used to fall back to
 *     N/A for any status it did not know, telling the client "this does not
 *     apply to you" about something nobody checked;
 *   * a coverage percentage without the not-verified count beside it.
 */

function technique(code: string, status: string): DashTechnique {
  return {
    code,
    name: `Technique ${code}`,
    tactic_name: "Execution",
    status: status as DashTechnique["status"],
    detection_tools: [],
    prevention_tools: [],
    response_tools: [],
    rationale: null,
  };
}

/** The technique's own table row. The status filter always renders every
 *  status as an <option>, so a page-wide `getAllByText` passes whatever the
 *  chip says (#621 review, finding 1). */
function row(code: string): HTMLElement {
  const tr = screen.getByText(code).closest("tr");
  if (!tr) throw new Error(`no table row for ${code}`);
  return tr;
}

function data(
  techniques: DashTechnique[],
  counts = { nv: 0, out: 0 },
): AttackDashboardData {
  return {
    service_id: "s1",
    service_title: "ATT&CK Coverage",
    released_at: "2026-09-01T12:00:00Z",
    deliverable_version: 1,
    rollup: {
      total_evaluated: 1,
      covered: 1,
      partial: 0,
      gap: 0,
      not_applicable: 0,
      outside_control_surface: counts.out,
      unable_to_determine: counts.nv,
      coverage_pct: 100,
      by_tactic: [],
    },
    techniques,
  };
}

describe("AttackDashboard, the two new statuses (#554)", () => {
  it("names an unverified technique 'Not verified', never N/A", () => {
    render(
      <AttackDashboard
        data={data([technique("T1190", "unable_to_determine")])}
      />,
    );
    const r = within(row("T1190"));
    expect(r.getByText("Not verified")).toBeInTheDocument();
    expect(r.queryByText("N/A")).toBeNull();
  });

  it("names a technique outside the control surface as such", () => {
    render(
      <AttackDashboard
        data={data([technique("T1190", "outside_control_surface")])}
      />,
    );
    expect(
      within(row("T1190")).getByText("Outside control surface"),
    ).toBeInTheDocument();
  });

  it("shows a status it does not know as unknown, never borrowing N/A", () => {
    render(<AttackDashboard data={data([technique("T1190", "bogus")])} />);
    expect(
      within(row("T1190")).getByText("Unknown status"),
    ).toBeInTheDocument();
  });

  it("states the not-verified count beside every percentage, even at zero", () => {
    // Three places show a percentage: the coverage mix, the KPI row, and the
    // Detect / Prevent / Respond triad (#621 review, finding 2). Each carries
    // the sentence, so the count is exactly three -- dropping any one surface
    // turns this red.
    const { unmount } = render(
      <AttackDashboard
        data={data([technique("T1", "covered")], { nv: 7, out: 3 })}
      />,
    );
    expect(
      screen.getAllByText(/Not verified 7, Outside control surface 3\./),
    ).toHaveLength(3);
    unmount();
    render(<AttackDashboard data={data([technique("T1", "covered")])} />);
    expect(
      screen.getAllByText(/Not verified 0, Outside control surface 0\./),
    ).toHaveLength(3);
  });
});
