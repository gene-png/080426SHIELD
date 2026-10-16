import { describe, expect, it } from "vitest";

import type { TechDebtDashboardData } from "@/lib/dashboards/techDebt";

import { spendSub } from "./TechDebtDashboard";

// TD-5 (for #1060): the client spend subtitle states how many costs are AI
// estimates (copy E6, after any other text with " · "), and E7 makes any
// estimate "partial". Copy approved on #736 (6205600298, ruled 6206818759).

function partial(over: Partial<TechDebtDashboardData>): TechDebtDashboardData {
  return {
    spend_completeness: "partial",
    source_rows_total: 30,
    included_count: 30,
    excluded_count: 0,
    excluded_count_exact: true,
    no_cost_count: 0,
    ai_estimate_count: 0,
    ...over,
  } as TechDebtDashboardData;
}

describe("spendSub, AI-estimated costs (TD-5)", () => {
  it("states the estimates alone, not as a floor, when they are the only cause", () => {
    const out = spendSub(partial({ ai_estimate_count: 3 }));
    expect(out).toBe("3 costs are AI estimates");
    expect(out).not.toContain("Floor");
    expect(out).not.toContain("lacked a cost");
  });

  it("uses the singular for one estimate", () => {
    expect(spendSub(partial({ ai_estimate_count: 1 }))).toBe(
      "1 cost is an AI estimate",
    );
  });

  it("follows the no-cost count", () => {
    expect(spendSub(partial({ no_cost_count: 2, ai_estimate_count: 1 }))).toBe(
      "Floor - 2 tools have no cost; total excludes them · 1 cost is an AI estimate",
    );
  });

  it("follows an exclusion and the no-cost count", () => {
    expect(
      spendSub(
        partial({
          included_count: 27,
          excluded_count: 3,
          no_cost_count: 2,
          ai_estimate_count: 4,
        }),
      ),
    ).toBe(
      "Floor - 3 of 30 uploaded rows excluded · 2 tools have no cost; total excludes them · 4 costs are AI estimates",
    );
  });

  it("says nothing about estimates when there are none", () => {
    expect(spendSub(partial({ no_cost_count: 1 }))).toBe(
      "Floor - 1 tool has no cost; total excludes it",
    );
  });
  it("states the estimates on a list that was never reconciled too", () => {
    // The "unknown" note used to return before the estimates were read.
    expect(
      spendSub(
        partial({
          spend_completeness: "unknown",
          source_rows_total: null,
          ai_estimate_count: 2,
        }),
      ),
    ).toBe(
      "May not be complete - upload not reconciled · 2 costs are AI estimates",
    );
  });
});
