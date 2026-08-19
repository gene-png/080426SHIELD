import { describe, expect, it } from "vitest";

import {
  functionsByGap,
  hiddenGapCount,
  targetIsAssumed,
  type CsfDashboardData,
  type CsfFunction,
  type CsfGap,
} from "./csf";

function fn(over: Partial<CsfFunction> = {}): CsfFunction {
  return {
    code: "GV",
    name: "Govern",
    subcategory_count: 10,
    answered_count: 10,
    coverage_pct: 100,
    current_tier: 2,
    current_pct: 50,
    current_label: "Risk Informed",
    target_pct: 75,
    gap_pct: 25,
    gap_count: 4,
    weakest: [],
    ...over,
  };
}

function gap(over: Partial<CsfGap> = {}): CsfGap {
  return {
    code: "GV.OC-01",
    name: "Organizational context",
    function: "GV",
    function_name: "Govern",
    current_tier: 1,
    target_tier: 3,
    gap_size: 2,
    priority_score: 2.4,
    ...over,
  };
}

function data(over: Partial<CsfDashboardData> = {}): CsfDashboardData {
  return {
    service_id: "s1",
    service_title: "Atlas — CSF",
    released_at: "2026-08-19T00:00:00Z",
    deliverable_version: 1,
    overall_label: "Risk Informed",
    current_tier: 2,
    current_pct: 50,
    coverage_pct: 100,
    target_tier: 3,
    target_label: "Repeatable",
    target_pct: 75,
    target_tier_source: "client",
    total_gap_count: 37,
    largest_gap_function: "Govern",
    largest_gap_pct: 25,
    functions: [fn()],
    top_gaps: [gap()],
    ...over,
  };
}

describe("csf dashboard transforms", () => {
  it("functionsByGap: largest gap first", () => {
    const sorted = functionsByGap([
      fn({ name: "Govern", gap_pct: 10 }),
      fn({ name: "Detect", gap_pct: 50 }),
      fn({ name: "Recover", gap_pct: 25 }),
    ]);
    expect(sorted.map((f) => f.name)).toEqual(["Detect", "Recover", "Govern"]);
  });

  it("functionsByGap: does not mutate its input", () => {
    const input = [
      fn({ name: "Govern", gap_pct: 10 }),
      fn({ name: "Detect", gap_pct: 50 }),
    ];
    functionsByGap(input);
    expect(input.map((f) => f.name)).toEqual(["Govern", "Detect"]);
  });

  it("hiddenGapCount: states what the truncated list is NOT showing", () => {
    // The #75 shape: a client reading 20 of 37 remediation items with no
    // statement that anything was omitted.
    expect(
      hiddenGapCount(data({ total_gap_count: 37, top_gaps: [gap(), gap()] })),
    ).toBe(35);
  });

  it("hiddenGapCount: 0 when nothing is hidden, never negative", () => {
    expect(
      hiddenGapCount(data({ total_gap_count: 1, top_gaps: [gap()] })),
    ).toBe(0);
    // A shorter total than the list would be a backend bug, but the UI must not
    // render "-3 more" over it.
    expect(
      hiddenGapCount(data({ total_gap_count: 0, top_gaps: [gap(), gap()] })),
    ).toBe(0);
  });

  it("targetIsAssumed: false for the client's own intake choice", () => {
    expect(targetIsAssumed(data({ target_tier_source: "client" }))).toBe(false);
  });

  it("targetIsAssumed: true for the engine default, so a number nobody chose is marked", () => {
    expect(targetIsAssumed(data({ target_tier_source: "default" }))).toBe(true);
  });

  it("targetIsAssumed: treats an unknown source as assumed, not as chosen", () => {
    // Fail safe: a value this build does not recognise must not be presented as
    // the client's decision.
    expect(targetIsAssumed(data({ target_tier_source: "something_new" }))).toBe(
      true,
    );
  });
});
