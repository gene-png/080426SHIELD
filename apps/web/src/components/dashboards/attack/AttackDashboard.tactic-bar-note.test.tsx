import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type {
  AttackDashboardData,
  DashTechnique,
} from "@/lib/dashboards/attack";

import { AttackDashboard } from "./AttackDashboard";

/**
 * #1324: the "Coverage by tactic" chart counts a technique under every tactic
 * it belongs to, parents included; the blind-spot categories list each
 * technique once, under its first tactic. The chart says so, in the copy the
 * advisor approved verbatim (P-1, #736 6225076633); the literal below is
 * typed from that ruling, never read from the component.
 */

const P1 =
  'This chart counts a technique under every tactic it belongs to, and a parent technique as well as its sub-techniques, so its uncovered counts can be higher than the categories under "What you\'re blind to today", which list each technique once.';

function tech(partial: Partial<DashTechnique>): DashTechnique {
  return {
    code: "T0000",
    name: "Example",
    tactic_name: "Execution",
    status: "gap",
    detection_tools: [],
    prevention_tools: [],
    response_tools: [],
    rationale: null,
    computed_parent: false,
    sub_technique_count: 0,
    ...partial,
  };
}

function data(techniques: DashTechnique[]): AttackDashboardData {
  return {
    ai_source: {
      state: "live",
      sentence: "AI suggestions in this assessment came from a live AI model.",
      live_runs: 1,
      fixture_runs: 0,
    },
    service_id: "svc-1",
    service_title: "ATT&CK",
    released_at: "2026-05-12T00:00:00Z",
    deliverable_version: 1,
    rollup: {
      total_evaluated: techniques.length,
      covered: 0,
      partial: 0,
      gap: techniques.length,
      not_applicable: 0,
      outside_control_surface: 0,
      unable_to_determine: 0,
      coverage_pct: 0,
      coverage_measured: true,
      by_tactic: [],
    },
    techniques,
  };
}

describe("the Coverage by tactic chart says how it counts (#1324)", () => {
  it("states P-1 under the chart, verbatim", () => {
    render(<AttackDashboard data={data([tech({ code: "T1059" })])} />);
    const note = screen.getByTestId("attack-tactic-bar-counting");
    expect(note.textContent).toBe(P1);
    // It sits in the chart's own section, not elsewhere on the page.
    const section = screen
      .getByText("Coverage by tactic")
      .closest("section") as HTMLElement;
    expect(section).toContainElement(note);
  });
});
