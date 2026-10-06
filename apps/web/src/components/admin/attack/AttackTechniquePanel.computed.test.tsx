import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type {
  AttackCoverageRow,
  AttackHeatmap,
  CatalogTechnique,
} from "@/lib/attack/types";

import { AttackHeatmapCard } from "./AttackHeatmapCard";
import { AttackTechniquePanel } from "./AttackTechniquePanel";

/**
 * #554 R3 in the admin workspace: the technique panel's computed status (A7 of
 * the build plan on #554, written out) and the heatmap card's awaiting-review
 * sentence beside the percentage.
 */

const TECHNIQUE: CatalogTechnique = {
  id: "T1003.001",
  name: "LSASS Memory",
  tactics: ["TA0006"],
  is_sub_technique: true,
  parent_id: "T1003",
};
const LINE = "Detect: in place · Prevent: not in place · Respond: in place";

function row(over: Partial<AttackCoverageRow> = {}): AttackCoverageRow {
  return {
    id: "c1",
    assessment_id: "a1",
    technique_code: "T1003.001",
    status: "covered",
    reason_code: null,
    narrative: null,
    notes: null,
    evidence_artifact_id: null,
    answered_by: null,
    answered_at: null,
    computed_status: "partial",
    capabilities: {
      detect: "in_place",
      prevent: "not_in_place",
      respond: "in_place",
      line: LINE,
      awaiting_review: false,
      cannot_be_prevented: false,
    },
    ...over,
  };
}

function panel(coverage: AttackCoverageRow) {
  return render(
    <AttackTechniquePanel
      technique={TECHNIQUE}
      coverage={coverage}
      coverageDefinitions={[]}
      onPatch={vi.fn()}
      onConfirmCitations={vi.fn()}
    />,
  );
}

describe("AttackTechniquePanel, a computed status (#554 R3)", () => {
  it("names the computed status and the AI's suggestion when they differ", () => {
    panel(row());
    const block = screen.getByTestId("computed-status");
    expect(block).toHaveTextContent(
      "Computed status: Partial (AI suggested: Covered)",
    );
    expect(block).toHaveTextContent(LINE);
  });

  it("names only the computed status when they agree", () => {
    panel(row({ status: "partial" }));
    const block = screen.getByTestId("computed-status");
    expect(block.firstChild).toHaveTextContent(/^Computed status: Partial$/);
  });

  it("says nothing of it before R3", () => {
    panel(row({ computed_status: null, capabilities: null }));
    expect(screen.getByText(/LSASS Memory/)).toBeInTheDocument();
    expect(screen.queryByTestId("computed-status")).toBeNull();
  });
});

function heatmap(over: Partial<AttackHeatmap> = {}): AttackHeatmap {
  return {
    assessment_id: "a1",
    version: 1,
    total_techniques: 222,
    total_sub_techniques: 475,
    scored_count: 10,
    unscored_count: 687,
    catalogue_count: 697,
    covered: 4,
    partial: 2,
    gap: 4,
    not_applicable: 0,
    outside_control_surface: 0,
    unable_to_determine: 0,
    coverage_pct: 50,
    coverage_measured: true,
    by_tactic: [],
    ...over,
  };
}

describe("AttackHeatmapCard, awaiting review (#554 R3)", () => {
  it("prints the API's sentence beside the percentage", () => {
    const sentence =
      "2 techniques list tools awaiting review; they are scored as if those tools were not in place.";
    render(
      <AttackHeatmapCard
        heatmap={heatmap({ awaiting_review_sentence: sentence })}
      />,
    );
    expect(
      screen.getByTestId("attack-heatmap-awaiting-review"),
    ).toHaveTextContent(sentence);
  });

  it("prints nothing when nothing awaits review", () => {
    render(<AttackHeatmapCard heatmap={heatmap()} />);
    expect(screen.getByText("Coverage 50%")).toBeInTheDocument();
    expect(screen.queryByTestId("attack-heatmap-awaiting-review")).toBeNull();
  });
});
