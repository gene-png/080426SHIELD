import { describe, expect, it } from "vitest";

import type { TechDebtDashboardData } from "@/lib/dashboards/techDebt";

import { spendSub } from "./TechDebtDashboard";

/**
 * #193 on the client dashboard. When the extraction could not attribute every
 * item to one uploaded row, the api says so (`excluded_count_exact: false`)
 * and `excluded_count` is a FLOOR -- printed as "at least", never as the
 * count -- and 0 when items were as many as rows, the case that read
 * "complete".
 */
function partial(over: Partial<TechDebtDashboardData>): TechDebtDashboardData {
  return {
    spend_completeness: "partial",
    source_rows_total: 3,
    included_count: 3,
    excluded_count: 0,
    excluded_count_exact: false,
    ...over,
  } as TechDebtDashboardData;
}

describe("spendSub, an unknown exclusion count (#193)", () => {
  it("states the floor as a floor", () => {
    expect(spendSub(partial({ included_count: 2, excluded_count: 1 }))).toBe(
      "Floor - at least 1 of 3 uploaded rows excluded",
    );
  });

  it("says the count could not be made when the floor is zero", () => {
    expect(spendSub(partial({}))).toBe(
      "May not be complete - excluded rows could not be counted",
    );
  });

  it("states an exact count as the count", () => {
    expect(
      spendSub(
        partial({
          excluded_count_exact: true,
          included_count: 2,
          excluded_count: 1,
        }),
      ),
    ).toBe("Floor - 1 of 3 uploaded rows excluded");
  });
});
