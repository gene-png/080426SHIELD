/**
 * #1215: a list that was never reconciled ("unknown") still states how many
 * tools its total leaves out, as the PDF, DOCX and XLSX for the same list do.
 * Approved on #736 (6216024281, T3): the TD-10 sentence joined with " · ".
 * Strings typed here, never imported from the component.
 */
import { describe, expect, it } from "vitest";

import { spendSub } from "./TechDebtDashboard";
import type { TechDebtDashboardData } from "@/lib/dashboards/techDebt";

function unknown(noCost: number): TechDebtDashboardData {
  return {
    spend_completeness: "unknown",
    excluded_count: 0,
    source_rows_total: null,
    included_count: 5,
    excluded_count_exact: true,
    no_cost_count: noCost,
  } as TechDebtDashboardData;
}

describe("spendSub, an unreconciled list (#1215)", () => {
  it("names the uncosted tools after the unreconciled note", () => {
    expect(spendSub(unknown(4))).toBe(
      "May not be complete - upload not reconciled · 4 tools have no cost; total excludes them",
    );
  });

  it("uses the singular for one", () => {
    expect(spendSub(unknown(1))).toBe(
      "May not be complete - upload not reconciled · 1 tool has no cost; total excludes it",
    );
  });

  it("adds nothing when every tool has a cost", () => {
    // POSITIVE CONTROL for the two cases above: the note itself is unchanged.
    expect(spendSub(unknown(0))).toBe(
      "May not be complete - upload not reconciled",
    );
  });
});
