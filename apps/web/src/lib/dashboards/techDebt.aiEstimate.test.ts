/**
 * TD-5 (for #1060), copy E5: an AI-estimated cost is labelled wherever it
 * appears, the client's inventory and redundancy rows included. Typed from
 * the approved copy (#736 6205600298), never imported from the module.
 */
import { describe, expect, it } from "vitest";

import { itemCost, type TechDebtItem } from "./techDebt";

function row(cost: number | null, ai_estimate: boolean): TechDebtItem {
  return {
    name: "Tool",
    vendor: null,
    category: null,
    function: null,
    annual_cost_usd: cost,
    license_count: null,
    disposition: null,
    notes: null,
    bundle: null,
    ai_estimate,
  };
}

describe("the client cost cell (TD-5)", () => {
  it("labels an AI-estimated cost", () => {
    expect(itemCost(row(12000, true))).toBe("$12K (AI estimate)");
  });

  it("does not label a supplied cost", () => {
    // POSITIVE CONTROL: a label on every cost would satisfy the case above.
    expect(itemCost(row(12000, false))).toBe("$12K");
  });
});
