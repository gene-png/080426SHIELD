import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CapabilityItem } from "@/lib/tech_debt/types";

import { EditableCapabilityTable } from "./EditableCapabilityTable";

vi.mock("@/lib/tech_debt/client", () => ({ patchCapabilityItem: vi.fn() }));

// #643: the step-2 table scrolled sideways at normal widths. The cause was the
// cells, not the page: an <input> or <select> with no width keeps its
// intrinsic width (about twenty characters), and seven of them plus two fixed
// columns come to far more than the admin content column. jsdom cannot measure
// layout, so these tests pin the mechanism instead: a fixed-layout table with
// a stated minimum, and every editable control sized to its cell. A control
// added later without the sizing brings the scroll back, and the second test
// goes red on it.
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

describe("EditableCapabilityTable layout (#643)", () => {
  it("lays the table out at a fixed layout with a stated minimum width", () => {
    render(<EditableCapabilityTable items={[ITEM]} onItemUpdate={() => {}} />);
    const table = screen.getByRole("table");
    expect(table).toHaveClass("table-fixed");
    expect(table).toHaveClass("min-w-[60rem]");
  });

  it("sizes every editable control to its cell rather than its intrinsic width", () => {
    render(<EditableCapabilityTable items={[ITEM]} onItemUpdate={() => {}} />);
    const controls = [
      ...screen.getAllByRole("textbox"),
      ...screen.getAllByRole("combobox"),
    ];
    // Not vacuous: name, vendor, category, function, cost, licences, notes,
    // and the disposition select.
    expect(controls).toHaveLength(8);
    for (const control of controls) {
      expect(control).toHaveClass("w-full", "min-w-0");
    }
  });
});
