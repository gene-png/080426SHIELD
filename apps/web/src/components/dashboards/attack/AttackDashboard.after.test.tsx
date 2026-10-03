import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { AttackHeatmap } from "@/lib/attack/types";
import type {
  AttackDashboardData,
  DashTechnique,
} from "@/lib/dashboards/attack";

import { AttackHeatmapCard } from "../../admin/attack/AttackHeatmapCard";
import { AttackDashboard } from "./AttackDashboard";

/**
 * #801: the coverage figure after planned changes, beside today's, on the
 * client dashboard (D1, D2, A1, A3) and the admin heatmap card (H1). The API
 * words them; these strings are the approved text on #801, written out.
 */

const D1 =
  "After planned changes: 50.0%, if the tools marked for planned retirement are cut and nothing else changes.";
const D2 = "This uses the current consolidation plan.";
const A1 = "2 techniques would score lower.";

function technique(code: string): DashTechnique {
  return {
    code,
    name: `Technique ${code}`,
    tactic_name: "Discovery",
    status: "covered",
    detection_tools: [],
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
    parents_computed: true,
    rollup: {
      total_evaluated: 3,
      covered: 3,
      partial: 0,
      gap: 0,
      not_applicable: 0,
      outside_control_surface: 0,
      unable_to_determine: 0,
      coverage_pct: 100,
      coverage_measured: true,
      by_tactic: [],
    },
    techniques: [technique("T1003.001")],
    ...extra,
  };
}

describe("AttackDashboard, coverage after planned changes (#801)", () => {
  it("states it beside today's figure, with the current-plan note", () => {
    render(
      <AttackDashboard data={data({ after_planned_changes: [D1, D2, A1] })} />,
    );
    expect(
      screen.getByText(
        (text) =>
          text.includes(
            "Weighted coverage across evaluated techniques: 100%.",
          ) && text.includes(`${D1} ${D2} ${A1}`),
      ),
    ).toBeInTheDocument();
  });

  it("states nothing where there is nothing to recount", () => {
    render(<AttackDashboard data={data()} />);
    expect(
      screen.getByText("Weighted coverage across evaluated techniques: 100%.", {
        exact: false,
      }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/After planned changes/)).toBeNull();
  });
});

function heatmap(over: Partial<AttackHeatmap> = {}): AttackHeatmap {
  return {
    assessment_id: "a1",
    version: 1,
    total_techniques: 222,
    total_sub_techniques: 475,
    scored_count: 3,
    unscored_count: 694,
    catalogue_count: 697,
    covered: 3,
    partial: 0,
    gap: 0,
    not_applicable: 0,
    outside_control_surface: 0,
    unable_to_determine: 0,
    coverage_pct: 100,
    coverage_measured: true,
    by_tactic: [],
    ...over,
  };
}

describe("AttackHeatmapCard, coverage after planned changes (#801)", () => {
  it("states it beside the percentage, with no current-plan note", () => {
    render(
      <AttackHeatmapCard
        heatmap={heatmap({ after_planned_changes: [D1, A1] })}
      />,
    );
    expect(
      screen.getByTestId("attack-heatmap-after-planned-changes"),
    ).toHaveTextContent(`${D1} ${A1}`);
  });

  it("states nothing where there is nothing to recount", () => {
    render(<AttackHeatmapCard heatmap={heatmap()} />);
    expect(screen.getByText("Coverage 100%")).toBeInTheDocument();
    expect(
      screen.queryByTestId("attack-heatmap-after-planned-changes"),
    ).toBeNull();
  });
});
