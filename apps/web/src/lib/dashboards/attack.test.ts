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
    computed_parent: false,
    sub_technique_count: 0,
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
    outside_control_surface: 0,
    unable_to_determine: 0,
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
        outside_control_surface: 0,
        unable_to_determine: 0,
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
        outside_control_surface: 0,
        unable_to_determine: 0,
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
        outside_control_surface: 0,
        unable_to_determine: 0,
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

  it("dprCoverage: a computed parent is counted through its sub-techniques only (#620)", () => {
    // Option (b), the coordinator's call pending Gene: a parent carries no tools
    // of its own (D-094), so counting it would add a zero-leg row per parent.
    // Here the parent CHANGES the answer: with it, Detect is 2 of 3 = 67%;
    // counted once, through its children, it is 2 of 2 = 100%.
    const parent = tech({ code: "T1001", computed_parent: true });
    const c1 = tech({ code: "T1001.001", detection_tools: ["Tool A"] });
    const c2 = tech({ code: "T1001.002", detection_tools: ["Tool A"] });
    const dpr = dprCoverage([parent, c1, c2]);
    expect(dpr.total).toBe(2);
    expect(dpr.detect).toEqual({ n: 2, pct: 100 });
  });

  it("(b) moves the triad and leaves the KPI row alone (#620)", () => {
    // D-094 says the KPI row and coverage_pct do not move under (b). Pinned
    // here: the same data, the parent flagged and unflagged. The triad must
    // differ -- or this test proves nothing -- and kpis() must not.
    const parent = tech({ code: "T1001" });
    const kids = [
      tech({ code: "T1001.001", detection_tools: ["Tool A"] }),
      tech({ code: "T1001.002", detection_tools: ["Tool A"] }),
    ];
    const flagged = {
      ...DATA,
      techniques: [{ ...parent, computed_parent: true }, ...kids],
    };
    const unflagged = { ...DATA, techniques: [parent, ...kids] };
    expect(dprCoverage(flagged.techniques)).not.toEqual(
      dprCoverage(unflagged.techniques),
    );
    expect(kpis(flagged)).toEqual(kpis(unflagged));
    expect(kpis(flagged)).toEqual(kpis(DATA));
  });

  it("dprCoverage: the two #554 statuses leave both sides of the fraction", () => {
    // #621 review, finding 2. Fifty verified covered rows beside fifty rows
    // nobody verified must read "Detect 100%" with the fifty counted beside
    // it, not "Detect 50%" over a population the owner excluded.
    const assessed = tech({ code: "T1", detection_tools: ["Tool A"] });
    const unverified = tech({ code: "T2", status: "unable_to_determine" });
    const outside = tech({ code: "T3", status: "outside_control_surface" });
    const dpr = dprCoverage([assessed, unverified, outside]);
    expect(dpr.total).toBe(1);
    expect(dpr.detect.pct).toBe(100);
  });

  it("dprCoverage: N/A leaves the denominator, as the KPI row's does", () => {
    // Gene's decision, 2026-09-25 (D-092): the triad matches the KPI row, which
    // divides by covered + partial + gap. The N/A row CHANGES the answer -- it
    // was 1 of 2, 50%; it is 1 of 1, 100% -- so this cannot pass either way.
    const assessed = tech({ code: "T1", detection_tools: ["Tool A"] });
    const na = tech({ code: "T2", status: "not_applicable" });
    const dpr = dprCoverage([assessed, na]);
    expect(dpr.total).toBe(1);
    expect(dpr.detect).toEqual({ n: 1, pct: 100 });
  });

  it("dprCoverage: parents AND non-assessed rows leave the population together (#620 + #621)", () => {
    // The two PRs each narrowed the triad; this pins them combined. A parent,
    // its two children (one with Detect), an N/A row and an unverified row.
    // Only the two children count: Detect 1 of 2 = 50%. Dropping EITHER rule
    // changes the answer -- keeping the parent gives 1 of 3 (33%); keeping
    // N/A and unverified gives 1 of 4 (25%) -- so neither half passes alone.
    const parent = tech({ code: "T1001", computed_parent: true });
    const withTool = tech({ code: "T1001.001", detection_tools: ["Tool A"] });
    const without = tech({ code: "T1001.002" });
    const na = tech({ code: "T2", status: "not_applicable" });
    const unverified = tech({ code: "T3", status: "unable_to_determine" });
    const dpr = dprCoverage([parent, withTool, without, na, unverified]);
    expect(dpr.total).toBe(2);
    expect(dpr.detect).toEqual({ n: 1, pct: 50 });
    expect(dpr.excluded).toEqual({ parents: 1, pending: 0 });
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
