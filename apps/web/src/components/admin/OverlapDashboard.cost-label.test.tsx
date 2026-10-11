import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { OverlapAnalysis } from "@/lib/tech_debt/types";

import { OverlapDashboard } from "./OverlapDashboard";

/**
 * #781: the cost card never calls a partial figure a total. Its label is the
 * one the api sends (`total_cost_label`, the deliverable's own `cost_label`),
 * so this screen and the released document say the same thing about one list.
 * The three strings are the deliverable's, written out here.
 */

function analysis(label: string): OverlapAnalysis {
  return {
    capability_list_id: "l1",
    capability_list_version: 1,
    by_category: [],
    by_vendor: [],
    top_cost_items: [],
    total_cost: 30,
    total_items: 2,
    uncategorized_count: 0,
    no_vendor_count: 0,
    no_cost_count: 0,
    total_cost_label: label,
  };
}

describe("OverlapDashboard cost card (#781)", () => {
  for (const label of [
    "Total annual cost",
    "Included annual cost",
    "Annual cost (may not be complete)",
  ]) {
    it(`labels the figure "${label}" when the api says so`, () => {
      render(<OverlapDashboard analysis={analysis(label)} />);
      expect(screen.getByText(label)).toBeInTheDocument();
      expect(screen.getByText("$30")).toBeInTheDocument();
      if (label !== "Total annual cost") {
        expect(screen.queryByText("Total annual cost")).toBeNull();
      }
    });
  }
});
