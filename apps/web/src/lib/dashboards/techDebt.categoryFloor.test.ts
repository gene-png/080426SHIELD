/**
 * #1214: a category holding a tool with no cost is a FLOOR, and its tooltip
 * says so. Ruled on #736 (6216024281, T3), option (a): "≥ $X", with TD-10
 * copy 1 on a second line. No bar or axis text changes. Strings typed here.
 */
import { describe, expect, it } from "vitest";

import { spendBar, spendTooltip, type CategorySpend } from "./techDebt";

const SPEND: CategorySpend[] = [
  { category: "PAM", total_usd: 38000, count: 2, no_cost_count: 1 },
  { category: "EDR", total_usd: 195000, count: 2, no_cost_count: 0 },
  { category: "SIEM", total_usd: 0, count: 1, no_cost_count: 1 },
  { category: "IAM", total_usd: 12000, count: 3, no_cost_count: 2 },
];

describe("the spend-by-category tooltip (#1214)", () => {
  it("reads an exact figure when every tool in the category has a cost", () => {
    // POSITIVE CONTROL: without it, a marker on every figure would pass.
    expect(spendTooltip(SPEND[1])).toEqual(["$195,000"]);
  });

  it("reads a floor, with the singular count, when one tool has no cost", () => {
    expect(spendTooltip(SPEND[0])).toEqual([
      "≥ $38,000",
      "1 tool has no cost; total excludes it",
    ]);
  });

  it("reads a floor, with the plural count, when several have no cost", () => {
    expect(spendTooltip(SPEND[3])).toEqual([
      "≥ $12,000",
      "2 tools have no cost; total excludes them",
    ]);
  });

  it("says a $0 category made only of uncosted tools is a floor, not a zero", () => {
    expect(spendTooltip(SPEND[2])).toEqual([
      "≥ $0",
      "1 tool has no cost; total excludes it",
    ]);
  });

  it("keeps each bar's own row, so a tooltip reads its own category", () => {
    const bar = spendBar(SPEND, 3);
    expect(bar.labels).toEqual(["PAM", "EDR", "SIEM"]);
    expect(bar.rows.map((r) => r.category)).toEqual(bar.labels);
  });
});
