import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
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
    expect(screen.getAllByText("Not verified").length).toBeGreaterThan(0);
  });

  it("names a technique outside the control surface as such", () => {
    render(
      <AttackDashboard
        data={data([technique("T1190", "outside_control_surface")])}
      />,
    );
    expect(
      screen.getAllByText("Outside control surface").length,
    ).toBeGreaterThan(0);
  });

  it("shows a status it does not know as unknown, never borrowing N/A", () => {
    render(<AttackDashboard data={data([technique("T1190", "bogus")])} />);
    expect(screen.getByText("Unknown status")).toBeInTheDocument();
  });

  it("states the not-verified count beside the percentage, even at zero", () => {
    const { unmount } = render(
      <AttackDashboard
        data={data([technique("T1", "covered")], { nv: 7, out: 3 })}
      />,
    );
    expect(
      screen.getByText(/Not verified 7, Outside control surface 3\./),
    ).toBeInTheDocument();
    unmount();
    render(<AttackDashboard data={data([technique("T1", "covered")])} />);
    expect(
      screen.getByText(/Not verified 0, Outside control surface 0\./),
    ).toBeInTheDocument();
  });
});
