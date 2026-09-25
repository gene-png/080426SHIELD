import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { AttackCatalog, TacticHeatmapEntry } from "@/lib/attack/types";

import { AttackMatrix } from "./AttackMatrix";

/**
 * #554, #621 review finding 4. The tactic header shows a per-tactic "cov X%",
 * and X is over covered + partial + gap only. A tactic with one covered row
 * and twenty unverified ones read "cov 100%" with nothing beside it.
 */

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
  total_techniques: 1,
  total_sub_techniques: 0,
};

function entry(over: Partial<TacticHeatmapEntry>): TacticHeatmapEntry {
  return {
    tactic_id: "TA0001",
    tactic_name: "Tactic A",
    technique_count: 1,
    sub_technique_count: 0,
    covered: 1,
    partial: 0,
    gap: 0,
    not_applicable: 0,
    unscored: 0,
    outside_control_surface: 0,
    unable_to_determine: 0,
    coverage_pct: 100,
    ...over,
  };
}

function renderWith(hm: TacticHeatmapEntry) {
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

describe("AttackMatrix tactic header (#554)", () => {
  it("states the not-verified count beside the per-tactic percentage", () => {
    renderWith(entry({ unable_to_determine: 20, outside_control_surface: 2 }));
    expect(screen.getByText("cov 100%")).toBeInTheDocument();
    expect(
      screen.getByTestId("attack-matrix-outside-TA0001"),
    ).toHaveTextContent("Not verified 20, Outside control surface 2.");
  });

  it("states it at zero too, so 'none' and 'not shown' never look alike", () => {
    renderWith(entry({}));
    expect(
      screen.getByTestId("attack-matrix-outside-TA0001"),
    ).toHaveTextContent("Not verified 0, Outside control surface 0.");
  });
});
