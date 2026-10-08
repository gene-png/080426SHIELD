/**
 * The admin overlap buckets count LICENSES (for #835): a bundle and its named
 * parts are one license. Copy approved by the advisor on #736 (comment
 * 6056012075): "{n} overlapping licenses", singular "1 overlapping license".
 */
import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { OverlapAnalysis } from "@/lib/tech_debt/types";

import { OverlapDashboard } from "./OverlapDashboard";

function bucket(key: string, item_count: number, names: string[]) {
  return {
    key,
    item_count,
    total_cost: 120000,
    cost_known: true,
    item_ids: names.map((_, i) => `${key}-${i}`),
    item_names: names,
  };
}

function analysis(): OverlapAnalysis {
  return {
    capability_list_id: "l1",
    capability_list_version: 1,
    by_category: [
      // Three rows, two licenses: CrowdStrike beside two parts of one bundle.
      bucket("EDR", 2, [
        "CrowdStrike Falcon",
        "Microsoft Defender for Endpoint",
        "Microsoft Defender for Cloud Apps",
      ]),
    ],
    by_vendor: [bucket("Okta", 1, ["Okta"])],
    top_cost_items: [],
    total_cost: 120000,
    total_items: 4,
    uncategorized_count: 0,
    no_vendor_count: 0,
    no_cost_count: 0,
    total_cost_label: "Total annual cost",
  };
}

describe("OverlapDashboard bucket license count", () => {
  it("says licenses, not items, in the plural", () => {
    render(<OverlapDashboard analysis={analysis()} />);
    expect(screen.getByText("2 overlapping licenses")).toBeInTheDocument();
    expect(screen.queryByText(/overlapping items/)).toBeNull();
  });

  it("uses the singular for one license", () => {
    render(<OverlapDashboard analysis={analysis()} />);
    expect(screen.getByText("1 overlapping license")).toBeInTheDocument();
  });
});
