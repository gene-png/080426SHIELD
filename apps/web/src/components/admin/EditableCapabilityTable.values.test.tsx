import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CapabilityItem } from "@/lib/tech_debt/types";

vi.mock("@/lib/tech_debt/client", () => ({
  patchCapabilityItem: vi.fn(),
  proxyMessage: (err: unknown, fallback: string) =>
    err instanceof Error && err.message ? err.message : fallback,
}));

import { patchCapabilityItem } from "@/lib/tech_debt/client";

import { EditableCapabilityTable } from "./EditableCapabilityTable";

/**
 * #879, web half: a cost or licence count typed into the table is read as a
 * number or not at all. The parsers stripped characters in silence -- "2.9"
 * licences saved as 29, "1200/month" as 1200 -- and a refused save showed a bare
 * "Save failed" without the API's reason. Copy V4 is the plan's, pending the
 * advisor's approval on #736.
 */

const V4 = "Not a number, so it was not saved.";

const ITEM: CapabilityItem = {
  id: "item-1",
  capability_list_id: "list-1",
  name: "Tool",
  vendor: "Vendor",
  category: "Category",
  function: "Function",
  annual_cost_usd: 1000,
  license_count: 10,
  notes: "n",
  confidence_pct: 90,
  source_artifact_id: null,
  disposition: null,
  disposition_rationale: null,
  consolidation_target_id: null,
};

function typeInto(label: string, value: string) {
  const input = screen.getByRole("textbox", { name: label });
  fireEvent.change(input, { target: { value } });
  fireEvent.blur(input);
}

describe("EditableCapabilityTable values (#879)", () => {
  beforeEach(() => {
    vi.mocked(patchCapabilityItem).mockReset();
    vi.mocked(patchCapabilityItem).mockResolvedValue(ITEM);
  });

  it.each([
    ["License count", "2.9"],
    ["License count", "ten"],
    ["Annual cost USD", "1200/month"],
    ["Annual cost USD", "€1,200"],
  ])("%s %s is refused in the cell and nothing is sent", (label, value) => {
    render(<EditableCapabilityTable items={[ITEM]} onItemUpdate={() => {}} />);
    typeInto(label, value);
    expect(screen.getByText(V4)).toBeInTheDocument();
    expect(patchCapabilityItem).not.toHaveBeenCalled();
  });

  it.each([
    ["Annual cost USD", "$1,200", { annual_cost_usd: 1200 }],
    ["Annual cost USD", "1,200.50", { annual_cost_usd: 1200.5 }],
    ["License count", "1,000", { license_count: 1000 }],
    ["License count", "", { license_count: null }],
  ])("%s %s is saved as written", async (label, value, patch) => {
    render(<EditableCapabilityTable items={[ITEM]} onItemUpdate={() => {}} />);
    typeInto(label, value);
    await waitFor(() =>
      expect(patchCapabilityItem).toHaveBeenCalledWith("item-1", patch),
    );
    expect(screen.queryByText(V4)).toBeNull();
  });

  it("shows the API's reason when it refuses a save", async () => {
    vi.mocked(patchCapabilityItem).mockRejectedValue(
      new Error(
        "License count must be a whole number between 0 and 2,147,483,647.",
      ),
    );
    render(<EditableCapabilityTable items={[ITEM]} onItemUpdate={() => {}} />);
    typeInto("License count", "3000000000");
    expect(
      await screen.findByText(
        "License count must be a whole number between 0 and 2,147,483,647.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Save failed")).toBeInTheDocument();
  });
});
