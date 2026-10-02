import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type {
  AttackCatalog,
  AttackHeatmap,
  TacticHeatmapEntry,
} from "@/lib/attack/types";
import type { AttackDashboardData } from "@/lib/dashboards/attack";

import { AttackHeatmapCard } from "./admin/attack/AttackHeatmapCard";
import { AttackMatrix } from "./admin/attack/AttackMatrix";
import { AttackDashboard } from "./dashboards/attack/AttackDashboard";

/**
 * #489, across all three renderers of an ATT&CK percentage. Where nothing is
 * Covered, Partial, Gap or pending review, `coverage_pct` is 0.0 -- the figure
 * an all-gap tactic also earns. The API says which with `coverage_measured`
 * (the exporter's own rule), and every screen says "not measured" there, as the
 * deliverable does. Each renderer is shown both halves: not measured reads
 * "not measured", and a MEASURED 0.0% still reads as a percentage.
 */

function heatmap(over: Partial<AttackHeatmap>): AttackHeatmap {
  return {
    assessment_id: "a1",
    version: 1,
    total_techniques: 1,
    total_sub_techniques: 0,
    scored_count: 0,
    unscored_count: 1,
    catalogue_count: 1,
    covered: 0,
    partial: 0,
    gap: 0,
    not_applicable: 0,
    outside_control_surface: 0,
    unable_to_determine: 0,
    coverage_pct: 0,
    coverage_measured: false,
    by_tactic: [],
    ...over,
  };
}

const CATALOG: AttackCatalog = {
  tactics: [
    { id: "TA0001", shortname: "a", name: "Tactic A", description: "" },
  ],
  techniques: [
    {
      id: "T1",
      name: "Technique 1",
      tactics: ["TA0001"],
      parent_id: null,
      is_sub_technique: false,
    },
  ],
  coverage_definitions: [],
  reason_codes: [],
  total_techniques: 1,
  total_sub_techniques: 0,
};

function tactic(over: Partial<TacticHeatmapEntry>): TacticHeatmapEntry {
  return {
    tactic_id: "TA0001",
    tactic_name: "Tactic A",
    technique_count: 1,
    sub_technique_count: 0,
    covered: 0,
    partial: 0,
    gap: 0,
    not_applicable: 0,
    unscored: 1,
    outside_control_surface: 0,
    unable_to_determine: 0,
    coverage_pct: 0,
    coverage_measured: false,
    ...over,
  };
}

function matrix(hm: TacticHeatmapEntry) {
  return render(
    <AttackMatrix
      catalog={CATALOG}
      coverageByCode={{}}
      heatmapByTactic={{ TA0001: hm }}
      onSelectTechnique={() => {}}
      selectedCode={null}
      showSubTechniques={false}
      onToggleSubTechniques={() => {}}
    />,
  );
}

function dashboard(measured: boolean, gap: number): AttackDashboardData {
  return {
    parents_computed: true,
    // #646 (Batch F): required since; not under test here.
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
      total_evaluated: gap,
      covered: 0,
      partial: 0,
      gap,
      not_applicable: 0,
      outside_control_surface: 0,
      unable_to_determine: 0,
      coverage_pct: 0,
      coverage_measured: measured,
      by_tactic: [],
    },
    techniques: [],
  };
}

describe("the admin heatmap card (#489)", () => {
  it("says 'Coverage not measured' where nothing was measured", () => {
    render(<AttackHeatmapCard heatmap={heatmap({})} />);
    expect(screen.getByText("Coverage not measured")).toBeInTheDocument();
    expect(screen.queryByText(/Coverage 0%/)).toBeNull();
  });

  it("still says 0% for a measured, all-gap assessment", () => {
    render(
      <AttackHeatmapCard
        heatmap={heatmap({ gap: 3, scored_count: 3, coverage_measured: true })}
      />,
    );
    expect(screen.getByText("Coverage 0%")).toBeInTheDocument();
    expect(screen.queryByText(/not measured/)).toBeNull();
  });
});

describe("the admin matrix tactic header (#489)", () => {
  it("says 'cov not measured' for a tactic nothing was measured in", () => {
    matrix(tactic({}));
    expect(screen.getByText("cov not measured")).toBeInTheDocument();
    expect(screen.queryByText("cov 0%")).toBeNull();
    // #554's counts stay beside it.
    expect(
      screen.getByTestId("attack-matrix-outside-TA0001"),
    ).toHaveTextContent("Not verified 0, Outside control surface 0.");
  });

  it("still says 'cov 0%' for a measured, all-gap tactic", () => {
    matrix(tactic({ gap: 1, unscored: 0, coverage_measured: true }));
    expect(screen.getByText("cov 0%")).toBeInTheDocument();
    expect(screen.queryByText(/not measured/)).toBeNull();
  });
});

describe("the client dashboard (#489)", () => {
  it("says the overall coverage was not measured, with the outside counts beside it", () => {
    render(<AttackDashboard data={dashboard(false, 0)} />);
    const desc = screen.getByText(
      /Weighted coverage across evaluated techniques: not measured/,
    );
    expect(desc).toHaveTextContent(
      "Weighted coverage across evaluated techniques: not measured — no technique has been judged Covered, Partial or Gap.",
    );
    expect(desc).toHaveTextContent("Not verified 0, Outside control surface 0");
    expect(screen.queryByText(/evaluated techniques: 0%/)).toBeNull();
  });

  it("still says 0% for a measured, all-gap assessment", () => {
    render(<AttackDashboard data={dashboard(true, 2)} />);
    expect(
      screen.getByText(/Weighted coverage across evaluated techniques: 0%\./),
    ).toBeInTheDocument();
    expect(screen.queryByText(/not measured/)).toBeNull();
  });
});
