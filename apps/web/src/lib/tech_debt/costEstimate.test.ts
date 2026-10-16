import { describe, expect, it } from "vitest";

import {
  aiEstimateItems,
  aiEstimateSentence,
  costEstimateResult,
  estimatePromptText,
  estimateResultLine,
} from "./costEstimate";

// TD-5 (for #1060). Copy typed from the approved proposal (#736 6205600298,
// ruled 6206818759 item 5), never imported from the module under test.

describe("the estimate rule", () => {
  it("counts only source rows whose cost the AI estimated", () => {
    const items = [
      {
        parent_item_id: null,
        annual_cost_usd: 100,
        cost_source: "ai_estimate",
      },
      { parent_item_id: null, annual_cost_usd: 100, cost_source: "consultant" },
      { parent_item_id: null, annual_cost_usd: 100, cost_source: null },
      {
        parent_item_id: null,
        annual_cost_usd: null,
        cost_source: "ai_estimate",
      },
      { parent_item_id: "b", annual_cost_usd: 100, cost_source: "ai_estimate" },
    ] as const;
    expect(aiEstimateItems(items)).toEqual([items[0]]);
  });
});

describe("copy", () => {
  it("E1, plural and singular", () => {
    expect(estimatePromptText(4)).toBe(
      "These 4 tools have no cost, or none was provided. Enter costs, or let AI estimate?",
    );
    expect(estimatePromptText(1)).toBe(
      "This tool has no cost, or none was provided. Enter a cost, or let AI estimate?",
    );
  });

  it("E6, plural, singular, and nothing at 0 or for a missing count", () => {
    expect(aiEstimateSentence(3)).toBe("3 costs are AI estimates");
    expect(aiEstimateSentence(1)).toBe("1 cost is an AI estimate");
    expect(aiEstimateSentence(0)).toBeNull();
    expect(aiEstimateSentence(undefined as unknown as number)).toBeNull();
  });

  it("E4 without refusals", () => {
    expect(
      estimateResultLine({
        asked: 5,
        estimated: 3,
        declined: 2,
        refused: {},
        stray_entries: 0,
      }),
    ).toBe(
      "3 of 5 tools estimated. 2 the AI could not estimate; they still have no cost.",
    );
  });

  it("E4 adds the refusals only when there are any", () => {
    expect(
      estimateResultLine({
        asked: 6,
        estimated: 3,
        declined: 1,
        refused: { changed_meanwhile: 1, invalid_cost: 1, omitted: 0 },
        stray_entries: 0,
      }),
    ).toBe(
      "3 of 6 tools estimated. 1 the AI could not estimate; they still have no cost. 2 estimates were refused (changed meanwhile: 1, invalid cost: 1).",
    );
  });
});

describe("reading a run's result", () => {
  const result = {
    asked: 2,
    estimated: 1,
    declined: 1,
    refused: {},
    stray_entries: 0,
  };

  it("reads a cost-estimate run", () => {
    expect(
      costEstimateResult({ purpose: "tech_debt.cost_estimate", result }),
    ).toEqual(result);
  });

  it("ignores any other run, such as an extraction", () => {
    expect(
      costEstimateResult({ purpose: "tech_debt_extract", result }),
    ).toBeNull();
  });

  it("says nothing, rather than 0 estimated, over a result it cannot read", () => {
    expect(
      costEstimateResult({
        purpose: "tech_debt.cost_estimate",
        result: { asked: 2 },
      }),
    ).toBeNull();
  });
});
