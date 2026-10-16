import "@testing-library/jest-dom/vitest";

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CapabilityList } from "@/lib/tech_debt/types";

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
