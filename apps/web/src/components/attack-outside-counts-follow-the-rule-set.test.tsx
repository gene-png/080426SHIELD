import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { outsideAssessedText } from "@/lib/attack/outsideAssessed";
import type { AttackHeatmap, TacticHeatmapEntry } from "@/lib/attack/types";
import {
  dprCoverage,
  type AttackDashboardData,
  type DashTechnique,
} from "@/lib/dashboards/attack";

import { AttackHeatmapCard } from "./admin/attack/AttackHeatmapCard";
import { AttackMatrix } from "./admin/attack/AttackMatrix";
import { AttackDashboard } from "./dashboards/attack/AttackDashboard";
import { ValueLoopCard, type ValueSummary } from "./home/ValueLoopCard";

/**
 * #621, option (a), decided 2026-09-26: the "Not verified N, Outside control
 * surface M" counts, the cards, filter options and triad population that carry
 * them render only for an assessment under #620's rules. The API decides that
 * with `attack/rules.py` and says so by sending the counts (and, on the client
 * dashboard, `parents_computed`); one approved before #620 arrives without
 * them and must render what was delivered.
 *
 * BOTH HALVES, per surface, from the same fixture with only the rule changed,
 * so neither half can pass for a change that did nothing.
 */

const ZERO = "Not verified 0, Outside control surface 0.";

function technique(code: string, status: string, tools = true): DashTechnique {
  return {
    code,
    name: `Technique ${code}`,
    tactic_name: "Execution",
    status: status as DashTechnique["status"],
    detection_tools: tools ? ["Tool A"] : [],
    prevention_tools: [],
    response_tools: [],
    rationale: null,
  };
}

function dashboard(newRules: boolean): AttackDashboardData {
  return {
    ...(newRules ? { parents_computed: true } : {}),
    service_id: "s1",
    service_title: "ATT&CK Coverage",
    released_at: "2026-09-01T12:00:00Z",
    deliverable_version: 1,
    rollup: {
      total_evaluated: 1,
      covered: 1,
      partial: 0,
      gap: 0,
      not_applicable: 1,
      ...(newRules
        ? { outside_control_surface: 0, unable_to_determine: 0 }
        : {}),
      coverage_pct: 100,
      by_tactic: [],
    },
    techniques: [
      technique("T1", "covered"),
      technique("T2", "not_applicable", false),
    ],
  };
}

describe("the client dashboard follows the rule set", () => {
  it("under rule 1 renders what was delivered: no counts, no new filters", () => {
    render(<AttackDashboard data={dashboard(false)} />);
    expect(screen.queryByText(/Not verified/)).toBeNull();
    expect(screen.queryByText(/Outside control surface/)).toBeNull();
    expect(
      screen.getByText("Coverage assessed this engagement"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Weighted coverage across evaluated techniques: 100%."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "A technique is fully covered only when all three legs are present.",
      ),
    ).toBeInTheDocument();
  });

  it("under the new rules states the counts and offers both statuses", () => {
    render(<AttackDashboard data={dashboard(true)} />);
    expect(
      screen.getByText(`Coverage assessed this engagement. ${ZERO}`),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        `Weighted coverage across evaluated techniques: 100%. ${ZERO}`,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "Not verified" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "Outside control surface" }),
    ).toBeInTheDocument();
  });
});

describe("a rule-2 payload missing the counts", () => {
  it("fails loudly instead of rendering like rule 1", () => {
    const d = dashboard(true);
    delete d.rollup.unable_to_determine;
    delete d.rollup.outside_control_surface;
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      expect(() => render(<AttackDashboard data={d} />)).toThrow(
        /parents_computed is set but the Not verified/,
      );
    } finally {
      spy.mockRestore();
    }
  });

  it("while rule-1 data without them renders", () => {
    render(<AttackDashboard data={dashboard(false)} />);
    expect(
      screen.getByText("Coverage assessed this engagement"),
    ).toBeInTheDocument();
  });
});

describe("the Detect / Prevent / Respond population follows the rule set", () => {
  const rows = [
    technique("T1", "covered"),
    technique("T2", "not_applicable", false),
  ];

  it("under rule 1 keeps N/A in the population, as delivered", () => {
    const dpr = dprCoverage(rows);
    expect(dpr.total).toBe(2);
    expect(dpr.detect).toEqual({ n: 1, pct: 50 });
  });

  it("under the new rules counts the assessed statuses only (D-092)", () => {
    const dpr = dprCoverage(rows, true);
    expect(dpr.total).toBe(1);
    expect(dpr.detect).toEqual({ n: 1, pct: 100 });
  });
});

describe("outsideAssessedText", () => {
  it("is null when the API did not send the counts", () => {
    expect(outsideAssessedText({})).toBeNull();
    expect(
      outsideAssessedText({
        unable_to_determine: null,
        outside_control_surface: null,
      }),
    ).toBeNull();
  });

  it("states both, at zero too, when it did", () => {
    expect(
      outsideAssessedText({
        unable_to_determine: 0,
        outside_control_surface: 0,
      }),
    ).toBe(ZERO);
  });
});

function heatmap(newRules: boolean): AttackHeatmap {
  return {
    assessment_id: "a1",
    version: 1,
    total_techniques: 193,
    total_sub_techniques: 440,
    scored_count: 10,
    unscored_count: 623,
    catalogue_count: 633,
    covered: 4,
    partial: 2,
    gap: 4,
    not_applicable: 0,
    outside_control_surface: newRules ? 0 : null,
    unable_to_determine: newRules ? 0 : null,
    coverage_pct: 50,
    by_tactic: [],
  };
}

describe("the admin heatmap card follows the rule set", () => {
  it("under rule 1 shows the definition, total and cards it had before #621", () => {
    render(<AttackHeatmapCard heatmap={heatmap(false)} loading={false} />);
    expect(screen.queryByTestId("attack-heatmap-outside-assessed")).toBeNull();
    expect(screen.queryByText("Not verified")).toBeNull();
    expect(screen.queryByText("Outside control surface")).toBeNull();
    expect(screen.getByText(/addressable excludes N\/A rows/)).toBeTruthy();
    expect(screen.getByText("10/633 scored")).toBeTruthy();
  });

  it("under the new rules states the counts and carries both cards", () => {
    render(<AttackHeatmapCard heatmap={heatmap(true)} loading={false} />);
    expect(
      screen.getByTestId("attack-heatmap-outside-assessed").textContent,
    ).toBe(ZERO);
    expect(screen.getByText("Not verified")).toBeTruthy();
    expect(screen.getByText("Outside control surface")).toBeTruthy();
    expect(screen.queryByText(/addressable excludes N\/A rows/)).toBeNull();
  });
});

function entry(newRules: boolean): TacticHeatmapEntry {
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
    outside_control_surface: newRules ? 0 : null,
    unable_to_determine: newRules ? 0 : null,
    coverage_pct: 100,
  };
}

function matrix(newRules: boolean) {
  return render(
    <AttackMatrix
      catalog={{
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
      }}
      coverageByCode={{}}
      heatmapByTactic={{ TA0001: entry(newRules) }}
      onSelectTechnique={() => {}}
      selectedCode={null}
      showSubTechniques={false}
      onToggleSubTechniques={() => {}}
    />,
  );
}

describe("the admin matrix header follows the rule set", () => {
  it("under rule 1 shows the percentage alone, as before #621", () => {
    matrix(false);
    expect(screen.getByText("cov 100%")).toBeTruthy();
    expect(screen.queryByTestId("attack-matrix-outside-TA0001")).toBeNull();
  });

  it("under the new rules states the counts beside it", () => {
    matrix(true);
    expect(screen.getByTestId("attack-matrix-outside-TA0001").textContent).toBe(
      ZERO,
    );
  });
});

function summary(notVerified: number | null): ValueSummary {
  return {
    tech_debt_savings_usd: null,
    tech_debt_savings_cost_known: true,
    tech_debt_savings_unresolved: false,
    zt_gap_count: null,
    zt_gap_unresolved: false,
    zt_services: 0,
    zt_targets_defaulted: null,
    zt_targets_unusable: null,
    zt_targets_computed_live: null,
    attack_uncovered_count: 2,
    attack_uncovered_unresolved: false,
    attack_uncovered_withheld: false,
    attack_not_verified_count: notVerified,
    csf_gap_count: null,
    csf_gap_unresolved: false,
    csf_services: 0,
    csf_targets_defaulted: null,
    csf_targets_unusable: null,
    csf_targets_computed_live: null,
    has_any_data: true,
    has_unresolved: false,
  };
}

describe("the home value card follows the rule set", () => {
  it("under rule 1 (no count sent) reads as it did before #621", () => {
    render(<ValueLoopCard summary={summary(null)} />);
    expect(screen.getByText("2 techniques uncovered")).toBeInTheDocument();
    expect(screen.queryByText(/not verified/i)).toBeNull();
    expect(
      screen.queryByText(/Not verified techniques were not checked/),
    ).toBeNull();
  });

  it("under the new rules states the count and says what it means", () => {
    render(<ValueLoopCard summary={summary(0)} />);
    expect(
      screen.getByText("2 techniques uncovered, 0 not verified"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Not verified techniques were not checked/),
    ).toBeInTheDocument();
  });
});
