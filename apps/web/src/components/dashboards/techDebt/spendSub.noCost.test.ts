import { describe, expect, it } from "vitest";

import type { TechDebtDashboardData } from "@/lib/dashboards/techDebt";

import { spendSub } from "./TechDebtDashboard";

// TD-10 (for #1048): the client "Annual license spend" subtitle says how many
// tools have no cost. It read "Floor - some tools lacked a cost", with no count,
// and dropped even that when rows were also excluded. Copy approved verbatim on
// #736 (6115773247; strings in 6115177462): the sentence follows any exclusion text after " · ".

function partial(over: Partial<TechDebtDashboardData>): TechDebtDashboardData {
  return {
    spend_completeness: "partial",
    source_rows_total: 30,
    included_count: 30,
    excluded_count: 0,
    excluded_count_exact: true,
    no_cost_count: 0,
    ...over,
  } as TechDebtDashboardData;
}

describe("spendSub, tools with no cost (TD-10)", () => {
  it("states the plural count", () => {
    expect(spendSub(partial({ no_cost_count: 4 }))).toBe(
      "Floor - 4 tools have no cost; total excludes them",
    );
  });

  it("uses the singular for one tool", () => {
    expect(spendSub(partial({ no_cost_count: 1 }))).toBe(
      "Floor - 1 tool has no cost; total excludes it",
    );
  });

  it("keeps the count when rows were also excluded", () => {
    expect(
      spendSub(
        partial({ included_count: 27, excluded_count: 3, no_cost_count: 4 }),
      ),
    ).toBe(
      "Floor - 3 of 30 uploaded rows excluded · 4 tools have no cost; total excludes them",
    );
  });

  it("keeps the count beside an exclusion count that is only a floor", () => {
    expect(
      spendSub(
        partial({
          included_count: 27,
          excluded_count: 3,
          excluded_count_exact: false,
          no_cost_count: 1,
        }),
      ),
    ).toBe(
      "Floor - at least 3 of 30 uploaded rows excluded · 1 tool has no cost; total excludes it",
    );
  });

  it("keeps the count beside an exclusion that could not be counted", () => {
    expect(
      spendSub(partial({ excluded_count_exact: false, no_cost_count: 2 })),
    ).toBe(
      "May not be complete - excluded rows could not be counted · 2 tools have no cost; total excludes them",
    );
  });

  // The RATCHET (TechDebtDashboard.tsx): unreachable from the current API,
  // kept on purpose. Pinned so it cannot be "simplified" into
  // `Floor - ${noCost}`, which would print "Floor - null" to a client.
  it.each([
    ["a zero count", 0],
    ["a missing count (an older API)", undefined],
  ])("keeps the count-free floor sentence for %s", (_label, count) => {
    expect(
      spendSub(partial({ no_cost_count: count as unknown as number })),
    ).toBe("Floor - some tools lacked a cost");
  });

  it("says nothing about cost when every tool has one", () => {
    const out = spendSub(
      partial({ included_count: 27, excluded_count: 3, no_cost_count: 0 }),
    );
    expect(out).toBe("Floor - 3 of 30 uploaded rows excluded");
  });
});
