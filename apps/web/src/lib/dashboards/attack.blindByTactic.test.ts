import { describe, expect, it } from "vitest";

import {
  blindByTactic,
  blindSpots,
  isKnownTactic,
  tacticSlug,
  type AttackDashboardData,
  type DashTactic,
  type DashTechnique,
} from "./attack";

/**
 * #1180: the blind spots grouped by category (each technique's first tactic),
 * in the catalog's tactic order, with counts that sum to the section's
 * "{n} uncovered" (the advisor's required test, #736 6216024281).
 */

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

function tactic(name: string): DashTactic {
  return {
    tactic_id: name,
    tactic_name: name,
    covered: 0,
    partial: 0,
    gap: 0,
    not_applicable: 0,
    unscored: 0,
    outside_control_surface: 0,
    unable_to_determine: 0,
    coverage_pct: 0,
    coverage_measured: false,
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
      // Catalog order, deliberately not alphabetical.
      by_tactic: [
        tactic("Persistence"),
        tactic("Execution"),
        tactic("Discovery"),
      ],
    },
    techniques,
  };
}

const WORLD = [
  tech({ code: "T1059", tactic_name: "Execution" }),
  tech({ code: "T1106", tactic_name: "Execution" }),
  tech({ code: "T1136", tactic_name: "Persistence" }),
  tech({ code: "T1001", tactic_name: "Command and Control" }),
  tech({ code: "T1610", tactic_name: "Execution", status: "covered" }),
  tech({ code: "T1600", tactic_name: "Persistence", computed_parent: true }),
];

describe("blindByTactic (#1180)", () => {
  it("groups each blind spot under its own tactic, in catalog order", () => {
    const groups = blindByTactic(data(WORLD));
    expect(groups.map((g) => [g.tactic, g.rows.map((r) => r.code)])).toEqual([
      ["Persistence", ["T1136"]],
      ["Execution", ["T1059", "T1106"]],
      // Not in by_tactic: after it.
      ["Command and Control", ["T1001"]],
    ]);
  });

  it("sums to the uncovered count the section states", () => {
    const d = data(WORLD);
    const total = blindByTactic(d).reduce((n, g) => n + g.rows.length, 0);
    // Computed independently here: gaps that are not computed parents.
    const uncovered = d.techniques.filter(
      (t) => t.status === "gap" && !t.computed_parent,
    ).length;
    expect(uncovered).toBe(4);
    expect(total).toBe(uncovered);
    expect(total).toBe(blindSpots(d.techniques).length);
  });

  it("gives each category a URL segment from its name", () => {
    expect(tacticSlug("Command and Control")).toBe("command-and-control");
    expect(tacticSlug("Credential Access")).toBe("credential-access");
    expect(blindByTactic(data(WORLD)).map((g) => g.slug)).toEqual([
      "persistence",
      "execution",
      "command-and-control",
    ]);
  });

  it("is empty when nothing is uncovered", () => {
    expect(blindByTactic(data([tech({ status: "covered" })]))).toEqual([]);
  });

  it("refuses a blind spot with no tactic rather than list a dead link", () => {
    expect(() =>
      blindByTactic(data([tech({ code: "T9999", tactic_name: "" })])),
    ).toThrow(/T9999 has no tactic/);
  });
});

describe("isKnownTactic (#1180 review F1)", () => {
  it("knows a catalog tactic with nothing uncovered", () => {
    expect(isKnownTactic(data(WORLD), "discovery")).toBe(true);
  });

  it("knows a tactic only a blind spot is listed under", () => {
    expect(isKnownTactic(data(WORLD), "command-and-control")).toBe(true);
  });

  it("does not know a name that is no tactic of the dashboard", () => {
    expect(isKnownTactic(data(WORLD), "defense-evasion")).toBe(false);
    expect(isKnownTactic(data(WORLD), "")).toBe(false);
  });
});
