/**
 * #1214: the chart's own tooltip wiring. `spendTooltip` is tested on its own
 * in techDebt.categoryFloor.test.ts; this renders the real `SpendByCategory`
 * with the chart library stubbed, takes the options it hands the chart, and
 * calls its tooltip callback per bar, so deleting or mis-indexing the
 * callback goes red here. Strings typed from the ruling (#736 6216024281).
 */
import "@testing-library/jest-dom/vitest";

import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CategorySpend } from "@/lib/dashboards/techDebt";

type Captured = {
  options: {
    plugins: {
      tooltip: {
        callbacks: { label: (c: { dataIndex: number }) => unknown };
      };
    };
  };
  data: { labels: string[] };
};
const captured = vi.hoisted((): Captured[] => []);

vi.mock("react-chartjs-2", () => ({
  Bar: (props: Captured) => {
    captured.push(props);
    return null;
  },
  Doughnut: () => null,
}));

import { SpendByCategory } from "./TechDebtCharts";

const SPEND: CategorySpend[] = [
  { category: "SIEM", total_usd: 380000, count: 1, no_cost_count: 0 },
  { category: "PAM", total_usd: 38000, count: 2, no_cost_count: 1 },
  { category: "IAM", total_usd: 0, count: 2, no_cost_count: 2 },
];

describe("SpendByCategory's tooltip (#1214)", () => {
  it("reads each bar's own category, a floor where a tool has no cost", () => {
    captured.length = 0;
    render(<SpendByCategory spend={SPEND} />);
    const { options, data } = captured[captured.length - 1];
    const label = options.plugins.tooltip.callbacks.label;
    // POSITIVE CONTROL: the bars are the three categories, in order.
    expect(data.labels).toEqual(["SIEM", "PAM", "IAM"]);
    expect(label({ dataIndex: 0 })).toEqual(["$380,000"]);
    expect(label({ dataIndex: 1 })).toEqual([
      "≥ $38,000",
      "1 tool has no cost; total excludes it",
    ]);
    expect(label({ dataIndex: 2 })).toEqual([
      "≥ $0",
      "2 tools have no cost; total excludes them",
    ]);
  });
});
