/**
 * A bundle part's Annual cost cell (for #927, inside #835). The bundle holds
 * the license value, so the API refuses a cost on a part. A part with NO
 * stored cost gets a read-only cell; a part carrying a cost stored before the
 * refusal keeps an editable cell, so the cost can be cleared. Approved by the
 * advisor on #736 (comment 6056012075).
 */
import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CapabilityItem } from "@/lib/tech_debt/types";

import { EditableCapabilityTable } from "./EditableCapabilityTable";

vi.mock("@/lib/tech_debt/client", () => ({ patchCapabilityItem: vi.fn() }));

function row(
  id: string,
  name: string,
  cost: number | null,
  parent: string | null,
): CapabilityItem {
  return {
    id,
    capability_list_id: "list-1",
    parent_item_id: parent,
    name,
    vendor: "Microsoft",
    category: "EDR",
    function: null,
    annual_cost_usd: cost,
    license_count: null,
    notes: null,
    confidence_pct: null,
    source_artifact_id: null,
    disposition: null,
    disposition_rationale: null,
    consolidation_target_id: null,
  };
}

// Rendered in this order: the bundle, then its parts.
const ITEMS = [
  row("bundle", "Microsoft 365 E5", 294120, null),
  row("part-new", "Microsoft Defender for Endpoint", null, "bundle"),
  row("part-legacy", "Microsoft Entra ID P2", 5000, "bundle"),
];

function costCells(): HTMLInputElement[] {
  return screen.getAllByLabelText("Annual cost USD") as HTMLInputElement[];
}

describe("EditableCapabilityTable bundle part cost cell", () => {
  it("is read-only for a part with no stored cost", () => {
    render(<EditableCapabilityTable items={ITEMS} onItemUpdate={() => {}} />);
    expect(costCells()[1]).toHaveAttribute("readonly");
  });

  it("stays editable for the bundle and for a part with a legacy cost", () => {
    render(<EditableCapabilityTable items={ITEMS} onItemUpdate={() => {}} />);
    const [bundle, , legacy] = costCells();
    expect(bundle).not.toHaveAttribute("readonly");
    expect(legacy).not.toHaveAttribute("readonly");
  });
});
