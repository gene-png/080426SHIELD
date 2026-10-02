import "@testing-library/jest-dom/vitest";

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type {
  AttackDashboardData,
  DashTechnique,
} from "@/lib/dashboards/attack";

import { AttackDashboard } from "./AttackDashboard";

/**
 * #554 R1 on the CLIENT dashboard: each Partial row says why it is partial.
 * The label sits under the Partial chip; the sentence is its title. The API
 * sends the wording (`attack/partial_reasons.py`); these strings are the
 * approved text on #554, written out.
 */

const REACH = {
  label: "Not covered everywhere",
  sentence:
    "Defended on most of your environment, but not on some systems, such as another operating system, a cloud or SaaS service, or unmanaged or off-network devices.",
};
const SET_BY = {
  label: "Set by its sub-techniques",
  sentence:
    "This technique's coverage is computed from its sub-techniques; see each sub-technique for its own coverage and reason.",
};

function technique(
  code: string,
  status: string,
  extra: Partial<DashTechnique> = {},
): DashTechnique {
  return {
    code,
    name: `Technique ${code}`,
    tactic_name: "Execution",
    status: status as DashTechnique["status"],
    detection_tools: [],
    prevention_tools: [],
    response_tools: [],
    rationale: null,
    ...extra,
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
    service_id: "s1",
    service_title: "ATT&CK Coverage",
    released_at: "2026-09-01T12:00:00Z",
    deliverable_version: 1,
    parents_computed: true,
    rollup: {
      total_evaluated: 3,
      covered: 1,
      partial: 2,
      gap: 0,
      not_applicable: 0,
      outside_control_surface: 0,
      unable_to_determine: 0,
      coverage_pct: 66.7,
      coverage_measured: true,
      by_tactic: [],
    },
    techniques,
  };
}

function row(code: string): HTMLElement {
  const tr = screen.getByText(code).closest("tr");
  if (!tr) throw new Error(`no table row for ${code}`);
  return tr;
}

describe("AttackDashboard, why a technique is Partial (#554 R1)", () => {
  it("shows the reason under the Partial chip, with its sentence as the title", () => {
    render(
      <AttackDashboard
        data={data([
          technique("T1190", "partial", { partial_reason: REACH }),
          technique("T1059", "covered"),
        ])}
      />,
    );
    const label = within(row("T1190")).getByText(REACH.label);
    expect(label).toHaveAttribute("title", REACH.sentence);
  });

  it("shows a computed parent's reason too", () => {
    render(
      <AttackDashboard
        data={data([
          technique("T1001", "partial", {
            computed_parent: true,
            sub_technique_count: 3,
            partial_reason: SET_BY,
          }),
        ])}
      />,
    );
    expect(within(row("T1001")).getByText(SET_BY.label)).toHaveAttribute(
      "title",
      SET_BY.sentence,
    );
  });

  it("shows nothing extra on a row with no reason", () => {
    render(<AttackDashboard data={data([technique("T1059", "covered")])} />);
    // APPEAR before ABSENT: the row renders, so the absence means something.
    expect(within(row("T1059")).getByText("Covered")).toBeInTheDocument();
    expect(within(row("T1059")).queryByText(REACH.label)).toBeNull();
  });
});

describe("AttackDashboard, the Partial-by-reason table (#554 R1)", () => {
  // The advisor's ruling (i), #736 18:34Z: the headers, and the caption,
  // approved as written.
  it("lists each reason with its count, and says they add up", () => {
    // Three Partials over two rows (2 + 1), so the caption's N is the
    // rollup's figure and cannot be confused with the number of rows.
    const base = data([
      technique("T1190", "partial", { partial_reason: REACH }),
    ]);
    render(
      <AttackDashboard
        data={{
          ...base,
          rollup: { ...base.rollup, partial: 3 },
          partial_reasons: [
            { ...REACH, count: 2 },
            { ...SET_BY, count: 1 },
          ],
        }}
      />,
    );
    const table = screen.getByRole("table", {
      name: "Partial coverage, by reason",
    });
    const t = within(table);
    for (const h of ["Reason", "What it means", "Techniques"]) {
      expect(t.getByRole("columnheader", { name: h })).toBeInTheDocument();
    }
    const reachRow = t.getByText(REACH.label).closest("tr") as HTMLElement;
    expect(within(reachRow).getByText(REACH.sentence)).toBeInTheDocument();
    expect(within(reachRow).getByText("2")).toBeInTheDocument();
    const setByRow = t.getByText(SET_BY.label).closest("tr") as HTMLElement;
    expect(within(setByRow).getByText("1")).toBeInTheDocument();
    expect(
      screen.getByText("These add up to the 3 Partial techniques above."),
    ).toBeInTheDocument();
  });

  it("renders no table when there is no Partial", () => {
    render(<AttackDashboard data={data([technique("T1059", "covered")])} />);
    expect(within(row("T1059")).getByText("Covered")).toBeInTheDocument();
    expect(
      screen.queryByRole("table", { name: "Partial coverage, by reason" }),
    ).toBeNull();
  });
});

describe("AttackDashboard, the reason table's caption agrees in number (#554 R1)", () => {
  // #743's defect: "the 1 Partial techniques". Singular approved for N = 1.
  function withTable(partial: number, counts: number[]) {
    const base = data([
      technique("T1190", "partial", { partial_reason: REACH }),
    ]);
    return {
      ...base,
      rollup: { ...base.rollup, partial },
      partial_reasons: counts.map((count, i) => ({
        ...(i === 0 ? REACH : SET_BY),
        count,
      })),
    };
  }

  it("reads in the singular for one Partial", () => {
    render(<AttackDashboard data={withTable(1, [1])} />);
    expect(
      screen.getByText("This adds up to the 1 Partial technique above."),
    ).toBeInTheDocument();
  });

  it("reads in the plural for two", () => {
    render(<AttackDashboard data={withTable(2, [1, 1])} />);
    expect(
      screen.getByText("These add up to the 2 Partial techniques above."),
    ).toBeInTheDocument();
  });
});
