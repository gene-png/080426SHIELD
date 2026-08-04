import { describe, expect, it } from "vitest";

import {
  filterItems,
  spendBar,
  sprawlDonut,
  usdCompact,
  usdFull,
  type CategorySpend,
  type TechDebtItem,
} from "./techDebt";

const SPEND: CategorySpend[] = [
  { category: "SIEM", total_usd: 380000, count: 1 },
  { category: "EDR", total_usd: 195000, count: 2 },
  { category: "PAM", total_usd: 133000, count: 2 },
];

function item(p: Partial<TechDebtItem>): TechDebtItem {
  return {
    name: "Tool",
    vendor: null,
    category: null,
    function: null,
    annual_cost_usd: null,
    license_count: null,
    disposition: null,
    notes: null,
    ...p,
  };
}

describe("tech debt dashboard transforms", () => {
  it("usdCompact: K/M abbreviations; zero and null are —", () => {
    expect(usdCompact(0)).toBe("—");
    expect(usdCompact(null)).toBe("—");
    expect(usdCompact(38000)).toBe("$38K");
    expect(usdCompact(1_200_000)).toBe("$1.2M");
  });

  it("usdFull: grouped thousands", () => {
    expect(usdFull(708000)).toBe("$708,000");
  });

  it("spendBar: top-N labels + values in order", () => {
    const b = spendBar(SPEND, 2);
    expect(b.labels).toEqual(["SIEM", "EDR"]);
    expect(b.values).toEqual([380000, 195000]);
  });

  it("sprawlDonut: category (count) labels", () => {
    const d = sprawlDonut([
      { category: "EDR", total_usd: 195000, count: 2 },
      { category: "PAM", total_usd: 133000, count: 3 },
    ]);
    expect(d.labels).toEqual(["EDR (2)", "PAM (3)"]);
    expect(d.values).toEqual([2, 3]);
  });

  it("filterItems: matches name/vendor/category", () => {
    const items = [
      item({ name: "CrowdStrike", category: "EDR" }),
      item({ name: "Splunk", vendor: "Splunk", category: "SIEM" }),
    ];
    expect(filterItems(items, "edr").map((i) => i.name)).toEqual([
      "CrowdStrike",
    ]);
    expect(filterItems(items, "splunk").map((i) => i.name)).toEqual(["Splunk"]);
    expect(filterItems(items, "")).toHaveLength(2);
  });
});
