import { describe, expect, it } from "vitest";

import {
  blindSpots,
  coverageMix,
  dprCoverage,
  filterTechniques,
  kpis,
  tacticBar,
  tacticOptions,
  type AttackDashboardData,
  type DashTechnique,
} from "./attack";

function tech(partial: Partial<DashTechnique>): DashTechnique {
  return {
    code: "T0000",
    name: "Example",
    tactic_name: "Execution",
    status: "covered",
    detection_tools: [],
    prevention_tools: [],
    response_tools: [],
    rationale: null,
    ...partial,
  };
}

const DATA: AttackDashboardData = {
  service_id: "s1",
  service_title: "Atlas — ATT&CK Coverage",
  released_at: "2026-05-12T00:00:00Z",
  deliverable_version: 1,
  rollup: {
    total_evaluated: 4,
    covered: 2,
    partial: 1,
    gap: 1,
    not_applicable: 0,
    coverage_pct: 62.5,
    by_tactic: [
      {
        tactic_id: "TA0002",
        tactic_name: "Execution",
        covered: 1,
        partial: 1,
        gap: 1,
        not_applicable: 0,
        unscored: 3,
        coverage_pct: 50,
      },
      {
        tactic_id: "TA0003",
        tactic_name: "Persistence",
        covered: 1,
        partial: 0,
        gap: 0,
        not_applicable: 0,
        unscored: 5,
        coverage_pct: 100,
      },
      {
        tactic_id: "TA0007",
        tactic_name: "Discovery",
        covered: 0,
        partial: 0,
        gap: 0,
        not_applicable: 0,
        unscored: 9,
        coverage_pct: 0,
      },
    ],
  },
  techniques: [
    tech({
      code: "T1059",
      name: "Command Interpreter",
      status: "covered",
      detection_tools: ["CrowdStrike"],
      prevention_tools: ["AppLocker"],
      response_tools: ["XSOAR"],
    }),
    tech({
      code: "T1106",
      name: "Native API",
      status: "partial",
      detection_tools: ["CrowdStrike"],
      prevention_tools: [],
      response_tools: [],
    }),
    tech({
      code: "T1136",
      name: "Create Account",
      tactic_name: "Persistence",
      status: "covered",
      detection_tools: ["Entra"],
      prevention_tools: ["SailPoint"],
      response_tools: [],
    }),
    tech({
      code: "T1610",
      name: "Deploy Container",
      status: "gap",
      detection_tools: [],
      prevention_tools: ["Wiz"],
      response_tools: [],
    }),
  ],
};

describe("attack dashboard transforms", () => {
  it("kpis: mix and percentages over the evaluated set", () => {
    const k = kpis(DATA);
    expect(k.evaluated).toBe(4);
    expect(k.covered).toEqual({ n: 2, pct: 50 });
    expect(k.partial).toEqual({ n: 1, pct: 25 });
    expect(k.blindSpots).toEqual({ n: 1, pct: 25 });
  });

  it("dprCoverage: a leg counts only when the tool list is non-empty", () => {
    const d = dprCoverage(DATA.techniques);
    expect(d.total).toBe(4);
    expect(d.detect.n).toBe(3); // T1059, T1106, T1136
    expect(d.prevent.n).toBe(3); // T1059, T1136, T1610
    expect(d.respond.n).toBe(1); // T1059 only
    expect(d.respond.pct).toBe(25);
  });

  it("dprCoverage: a withheld technique's unconfirmed tools do not count as posture", () => {
    // #102, found by the item-3b audit. A leg counted whenever a tool list was
    // non-empty — and the tools on a withheld row are exactly the UNCONFIRMED
    // ones, since the resolver applies them and flags them. So a run whose every
    // citation had to be inferred reported "Detect 100%" on the same page whose
    // rollup said 0 covered.
    //
    // A withheld technique leaves BOTH sides of the fraction, like `unscored`
    // and for the same reason: it is a claim not being made, not a claim of
    // absence. Scoring it as a zero would understate posture rather than decline
    // to state it.
    const confirmed = tech({ code: "T1", detection_tools: ["Splunk"] });
    const withheld = tech({
      code: "T2",
      detection_tools: ["CrowdStrike Falcon"],
      pending_review: true,
    });
    const dpr = dprCoverage([confirmed, withheld]);
    expect(dpr.total).toBe(1);
    expect(dpr.detect.n).toBe(1);
    expect(dpr.detect.pct).toBe(100);
  });

  it("dprCoverage: withholding everything reports no posture, not full posture", () => {
    const dpr = dprCoverage([
      tech({ detection_tools: ["CrowdStrike Falcon"], pending_review: true }),
    ]);
    expect(dpr.total).toBe(0);
    expect(dpr.detect.n).toBe(0);
    expect(dpr.detect.pct).toBe(0);
  });

  it("blindSpots: only gap techniques", () => {
    const b = blindSpots(DATA.techniques);
    expect(b.map((t) => t.code)).toEqual(["T1610"]);
  });

  it("tacticBar: drops tactics with no addressable techniques", () => {
    const bar = tacticBar(DATA.rollup.by_tactic);
    expect(bar.labels).toEqual(["Execution", "Persistence"]); // Discovery has 0
    expect(bar.covered).toEqual([1, 1]);
    expect(bar.gap).toEqual([1, 0]);
  });

  it("coverageMix: overall counts for the donut", () => {
    expect(coverageMix(DATA.rollup)).toEqual({
      covered: 2,
      partial: 1,
      gap: 1,
    });
  });

  it("filterTechniques: search matches id/name/tool; tactic + status filter", () => {
    expect(
      filterTechniques(DATA.techniques, {
        q: "sailpoint",
        tactic: "",
        status: "",
      }).map((t) => t.code),
    ).toEqual(["T1136"]);
    expect(
      filterTechniques(DATA.techniques, {
        q: "",
        tactic: "Execution",
        status: "",
      }).map((t) => t.code),
    ).toEqual(["T1059", "T1106", "T1610"]);
    expect(
      filterTechniques(DATA.techniques, {
        q: "",
        tactic: "",
        status: "gap",
      }).map((t) => t.code),
    ).toEqual(["T1610"]);
  });

  it("tacticOptions: sorted distinct tactics", () => {
    expect(tacticOptions(DATA.techniques)).toEqual([
      "Execution",
      "Persistence",
    ]);
  });
});
