import "@testing-library/jest-dom/vitest";

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type {
  AttackDashboardData,
  DashTechnique,
} from "@/lib/dashboards/attack";

import { AttackDashboard } from "./AttackDashboard";

/**
 * #620 round 3. A computed parent carries no tools of its own (D-094), so the
 * client page must render it AS computed -- never as "covered with no
 * detection, prevention or response" -- and must say which rows the triad and
 * the blind-spot list leave out, rather than narrowing them silently.
 */

function tech(over: Partial<DashTechnique>): DashTechnique {
  return {
    code: "T0000",
    name: "Technique",
    tactic_name: "Execution",
    status: "covered",
    computed_parent: false,
    sub_technique_count: 0,
    detection_tools: [],
    prevention_tools: [],
    response_tools: [],
    rationale: null,
    ...over,
  };
}

const PARENT = tech({
  code: "T1001",
  name: "Parent technique",
  status: "gap",
  computed_parent: true,
  sub_technique_count: 2,
});
const KIDS = [
  tech({ code: "T1001.001", status: "gap" }),
  tech({
    code: "T1001.002",
    status: "covered",
    detection_tools: ["Tool A"],
    prevention_tools: ["Tool A"],
    response_tools: ["Tool A"],
  }),
];
const PENDING = tech({ code: "T1002", pending_review: true });

function data(techniques: DashTechnique[]): AttackDashboardData {
  return {
    service_id: "s1",
    service_title: "ATT&CK Coverage",
    released_at: "2026-09-01T12:00:00Z",
    deliverable_version: 1,
    rollup: {
      total_evaluated: 4,
      covered: 2,
      partial: 0,
      gap: 2,
      not_applicable: 0,
      coverage_pct: 50,
      by_tactic: [],
    },
    techniques,
  };
}

function row(code: string): HTMLElement {
  const tr = screen
    .getAllByText(code)
    .map((el) => el.closest("tr"))
    .find((r): r is HTMLTableRowElement => r !== null);
  if (!tr) throw new Error(`no table row for ${code}`);
  return tr;
}

describe("AttackDashboard, a computed parent (#620 round 3)", () => {
  it("renders the parent's row as computed: no legs, and its sub-technique count", () => {
    render(<AttackDashboard data={data([PARENT, ...KIDS])} />);
    const r = within(row("T1001"));
    expect(r.getByText("From 2 sub-techniques")).toBeInTheDocument();
    for (const leg of ["D", "P", "R"]) {
      expect(r.queryByText(leg)).toBeNull();
    }
    // A standalone row keeps its legs.
    expect(within(row("T1001.002")).getByText("D")).toBeInTheDocument();
  });

  it("says which rows the triad leaves out, beside its percentages", () => {
    render(<AttackDashboard data={data([PARENT, ...KIDS, PENDING])} />);
    expect(screen.getByTestId("attack-triad-population")).toHaveTextContent(
      "Over 2 techniques. Not counted here: 1 parent technique, counted through its sub-techniques, and 1 pending review.",
    );
  });

  it("lists blind spots through sub-techniques, and says so", () => {
    render(<AttackDashboard data={data([PARENT, ...KIDS])} />);
    const section = screen
      .getByText("What you're blind to today")
      .closest("section") as HTMLElement;
    expect(within(section).getByText("1 uncovered")).toBeInTheDocument();
    expect(within(section).queryByText("Parent technique")).toBeNull();
    expect(section.textContent).toContain(
      "A technique with sub-techniques is listed through them.",
    );
  });
});
