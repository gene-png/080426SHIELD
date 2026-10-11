/**
 * The inventory pill once a bundle has been split into parts (for #835).
 *
 * "Applications" counts source items; the inventory table still lists every
 * row, parts included. Without this the pill read "6 tools" beside an
 * Applications card reading 4. Copy approved by the advisor on #736.
 */
import { describe, expect, it } from "vitest";

import { inventoryPill } from "./TechDebtDashboard";
import type { TechDebtDashboardData } from "@/lib/dashboards/techDebt";

function data(
  total_applications: number,
  bundle_part_count: number,
): TechDebtDashboardData {
  return {
    total_applications,
    bundle_part_count,
    items: Array.from({ length: total_applications + bundle_part_count }),
  } as unknown as TechDebtDashboardData;
}

describe("inventoryPill", () => {
  it("is unchanged when nothing was split", () => {
    expect(inventoryPill(data(5, 0))).toBe("5 tools");
  });

  it("names the parts separately from the tools", () => {
    expect(inventoryPill(data(4, 2))).toBe("4 tools, 2 bundle parts");
  });

  it("uses the singular for one tool and one part", () => {
    expect(inventoryPill(data(1, 1))).toBe("1 tool, 1 bundle part");
  });
});
