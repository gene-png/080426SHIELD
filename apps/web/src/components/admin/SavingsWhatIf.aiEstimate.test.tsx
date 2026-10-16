import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "@/lib/tech_debt/client";
import type { CapabilityList, SavingsPreview } from "@/lib/tech_debt/types";

import { SavingsWhatIf } from "./SavingsWhatIf";

vi.mock("@/lib/tech_debt/client", () => ({
  previewSavings: vi.fn(),
  bulkSetDisposition: vi.fn(),
  proxyMessage: (err: unknown, fallback: string) =>
    err instanceof Error ? err.message : fallback,
}));

/**
 * TD-5 (for #1060): the savings what-if's own table labels an AI-estimated
 * cost (copy E5, "AI estimate", approved on #736 6205600298), so a consultant
 * deciding what to cut sees which costs are guesses. Typed here.
 */

function list(): CapabilityList {
  return {
    id: "list-1",
    service_id: "svc-1",
    version: 1,
    status: "draft",
    items: [
      {
        id: "wiz",
        name: "Wiz",
        annual_cost_usd: 12000,
        cost_source: "ai_estimate",
        disposition: null,
      },
      {
        id: "splunk",
        name: "Splunk",
        annual_cost_usd: 480000,
        cost_source: null,
        disposition: "cut",
      },
    ],
  } as unknown as CapabilityList;
}

describe("SavingsWhatIf and AI estimates (TD-5)", () => {
  it("labels the estimated cost and not the supplied one", () => {
    render(
      <SavingsWhatIf
        list={list()}
        planSavings={480000}
        planKnown
        planEstimateCount={0}
        readOnly={false}
        onApplied={vi.fn()}
      />,
    );
    const row = (name: RegExp) => screen.getByRole("row", { name });
    expect(
      within(row(/Wiz/)).getByText("$12,000 (AI estimate)"),
    ).toBeInTheDocument();
    // POSITIVE CONTROL: a supplied cost reads as before.
    expect(within(row(/Splunk/)).getByText("$480,000")).toBeInTheDocument();
  });
});

/**
 * #1299 (TD-5), no admin exemption (#736 issuecomment-6225076633): the
 * what-if's two savings figures each say how many AI-estimated costs they
 * include (copy E6, spelled out here, not imported).
 */
describe("SavingsWhatIf savings figures and AI estimates (#1299)", () => {
  const m = vi.mocked(client);
  beforeEach(() => {
    vi.useFakeTimers();
    m.previewSavings.mockReset();
  });
  afterEach(() => vi.useRealTimers());

  function renderWith(planEstimateCount: number): void {
    render(
      <SavingsWhatIf
        list={list()}
        planSavings={480000}
        planKnown
        planEstimateCount={planEstimateCount}
        readOnly={false}
        onApplied={vi.fn()}
      />,
    );
  }

  it("states the estimate under the plan's figure", () => {
    renderWith(1);
    expect(screen.getByTestId("what-if-current")).toHaveTextContent("$480,000");
    expect(screen.getByTestId("what-if-current-estimates")).toHaveTextContent(
      "1 cost is an AI estimate",
    );
  });

  it("says nothing under the plan's figure when it includes no estimate", () => {
    renderWith(0);
    // Positive state first, then the absence.
    expect(screen.getByTestId("what-if-current")).toHaveTextContent("$480,000");
    expect(screen.queryByTestId("what-if-current-estimates")).toBeNull();
  });

  it("states the estimates under the what-if figure, from the server's count", async () => {
    const preview: SavingsPreview = {
      capability_list_id: "list-1",
      estimated_annual_savings: 492000,
      savings_cost_known: true,
      savings_ai_estimate_count: 2,
      keep_count: 0,
      consolidate_count: 0,
      cut_count: 2,
      undecided_count: 0,
    };
    m.previewSavings.mockResolvedValue(preview);
    renderWith(0);
    fireEvent.change(
      screen.getByRole("combobox", { name: "What-if for Wiz" }),
      { target: { value: "cut" } },
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });
    expect(screen.getByTestId("what-if-savings")).toHaveTextContent("$492,000");
    expect(screen.getByTestId("what-if-savings-estimates")).toHaveTextContent(
      "2 costs are AI estimates",
    );
  });
});
