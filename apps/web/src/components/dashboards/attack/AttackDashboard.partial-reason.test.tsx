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
const DIFFER = {
  label: "Sub-techniques differ",
  sentence:
    "Its sub-techniques are covered to different degrees; each sub-technique states its own reason.",
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
            partial_reason: DIFFER,
          }),
        ])}
      />,
    );
    expect(within(row("T1001")).getByText(DIFFER.label)).toHaveAttribute(
      "title",
      DIFFER.sentence,
    );
  });

  it("shows nothing extra on a row with no reason", () => {
    render(<AttackDashboard data={data([technique("T1059", "covered")])} />);
    // APPEAR before ABSENT: the row renders, so the absence means something.
    expect(within(row("T1059")).getByText("Covered")).toBeInTheDocument();
    expect(within(row("T1059")).queryByText(REACH.label)).toBeNull();
  });
});
