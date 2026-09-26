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

function data(
  techniques: DashTechnique[],
  parentsComputed = true,
): AttackDashboardData {
  return {
    ...(parentsComputed ? { parents_computed: true } : {}),
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
      // #621 option (a): the API sends these exactly when it sends
      // parents_computed, and refuses to build a response otherwise, so a
      // rule-2 fixture without them was a state the system cannot produce.
      // No tactic rows here, so there is nothing per tactic to add.
      ...(parentsComputed
        ? { outside_control_surface: 0, unable_to_determine: 0 }
        : {}),
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

  it("reconciles the Blind spots KPI with the blind-spot list on screen", () => {
    // #620 round 5. The KPI stays the rollup's (main's) count, over the same
    // population as coverage_pct, so covered + partial + blind spots sum to
    // 100%. The list is gaps through sub-techniques, so for rule 2 the section
    // says what the difference is. A world the app produces: a gap parent is
    // computed from children that are all gaps, and the rollup counts all 3.
    const parent = tech({
      code: "T1001",
      name: "Parent technique",
      status: "gap",
      computed_parent: true,
      sub_technique_count: 2,
    });
    const kids = [
      tech({ code: "T1001.001", status: "gap" }),
      tech({ code: "T1001.002", status: "gap" }),
    ];
    const d = data([parent, ...kids]);
    d.rollup = {
      ...d.rollup,
      total_evaluated: 3,
      covered: 0,
      partial: 0,
      gap: 3,
      coverage_pct: 0,
    };
    render(<AttackDashboard data={d} />);
    const kpi = screen.getByText("Blind spots").parentElement as HTMLElement;
    expect(kpi.textContent).toMatch(/^Blind spots3 · 100%/);
    const section = screen
      .getByText("What you're blind to today")
      .closest("section") as HTMLElement;
    expect(within(section).getByText("2 uncovered")).toBeInTheDocument();
    expect(
      within(section).getByTestId("attack-blind-reconcile"),
    ).toHaveTextContent(
      "The Blind spots figure above counts 3: the 2 listed here, and 1 parent technique whose gap is listed through its sub-techniques.",
    );
  });

  it("says nothing when the KPI and the list already agree", () => {
    // #620 round 6. A producible rule-2 world with no gap PARENT: a partial
    // parent over one gap child and one covered child. The rollup counts 1 gap
    // and the list shows 1, so no reconciliation -- never "and 0 parent
    // techniques".
    const parent = tech({
      code: "T1001",
      status: "partial",
      computed_parent: true,
      sub_technique_count: 2,
    });
    const kids = [
      tech({ code: "T1001.001", status: "gap" }),
      tech({
        code: "T1001.002",
        status: "covered",
        detection_tools: ["Tool A"],
      }),
    ];
    const d = data([parent, ...kids]);
    d.rollup = {
      ...d.rollup,
      total_evaluated: 3,
      covered: 1,
      partial: 1,
      gap: 1,
    };
    render(<AttackDashboard data={d} />);
    const section = screen
      .getByText("What you're blind to today")
      .closest("section") as HTMLElement;
    expect(within(section).getByText("1 uncovered")).toBeInTheDocument();
    expect(screen.queryByTestId("attack-blind-reconcile")).toBeNull();
  });

  it("reconciles in the plural when several parents are counted", () => {
    // Two gap parents (each over gap children): the rollup counts 5 gaps,
    // the list shows the 3 children.
    const p1 = tech({
      code: "T1001",
      status: "gap",
      computed_parent: true,
      sub_technique_count: 2,
    });
    const p2 = tech({
      code: "T1003",
      status: "gap",
      computed_parent: true,
      sub_technique_count: 1,
    });
    const kids = [
      tech({ code: "T1001.001", status: "gap" }),
      tech({ code: "T1001.002", status: "gap" }),
      tech({ code: "T1003.001", status: "gap" }),
    ];
    const d = data([p1, p2, ...kids]);
    d.rollup = {
      ...d.rollup,
      total_evaluated: 5,
      covered: 0,
      partial: 0,
      gap: 5,
      coverage_pct: 0,
    };
    render(<AttackDashboard data={d} />);
    expect(screen.getByTestId("attack-blind-reconcile")).toHaveTextContent(
      "The Blind spots figure above counts 5: the 3 listed here, and 2 parent techniques whose gaps are listed through their sub-techniques.",
    );
  });

  it("renders an assessment approved before #620 exactly as delivered", () => {
    // Gene's condition (D-094): the API omits the new keys for it, so every
    // row renders the old way -- legs and own tools -- and neither new
    // sentence appears.
    const legacy = [
      { ...PARENT, computed_parent: undefined, sub_technique_count: undefined },
      ...KIDS.map((k) => ({
        ...k,
        computed_parent: undefined,
        sub_technique_count: undefined,
      })),
    ];
    render(<AttackDashboard data={data(legacy, false)} />);
    expect(within(row("T1001")).getByText("D")).toBeInTheDocument();
    expect(screen.queryByText(/From \d+ sub-techniques/)).toBeNull();
    expect(screen.queryByTestId("attack-triad-population")).toBeNull();
    expect(document.body.textContent).not.toContain(
      "A technique with sub-techniques is listed through them.",
    );
  });
});
