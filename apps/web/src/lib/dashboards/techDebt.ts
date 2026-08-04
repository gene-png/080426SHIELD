/**
 * Client Tech Debt (software portfolio) dashboard — types + pure transforms
 * (D-035). Mirrors the backend `TechDebtDashboardResponse`.
 */

export interface TechDebtItem {
  name: string;
  vendor: string | null;
  category: string | null;
  function: string | null;
  annual_cost_usd: number | null;
  license_count: number | null;
  disposition: string | null;
  notes: string | null;
}

export interface CategorySpend {
  category: string;
  total_usd: number;
  count: number;
}

export interface Redundancy {
  category: string;
  count: number;
  savings_usd: number;
  items: TechDebtItem[];
}

export interface TechDebtDashboardData {
  service_id: string;
  service_title: string;
  released_at: string;
  deliverable_version: number;
  total_applications: number;
  annual_spend_usd: number;
  identified_savings_usd: number;
  savings_cost_known: boolean;
  redundant_category_count: number;
  spend_by_category: CategorySpend[];
  sprawl_by_category: CategorySpend[];
  redundancies: Redundancy[];
  items: TechDebtItem[];
}

/** Compact USD (e.g. $195K, $1.2M, — for zero). */
export function usdCompact(n: number | null): string {
  if (n === null || n === 0) return "—";
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `$${Math.round(n / 1000)}K`;
  return `$${n}`;
}

/** Full USD (e.g. $708,000). */
export function usdFull(n: number): string {
  return `$${Math.round(n).toLocaleString("en-US")}`;
}

export interface BarData {
  labels: string[];
  values: number[];
}

/** Top-N categories by spend for the horizontal bar. */
export function spendBar(spend: CategorySpend[], topN = 10): BarData {
  const rows = spend.slice(0, topN);
  return {
    labels: rows.map((s) => s.category),
    values: rows.map((s) => s.total_usd),
  };
}

/** Tool-count-per-category (only sprawled categories) for the doughnut. */
export function sprawlDonut(sprawl: CategorySpend[]): BarData {
  return {
    labels: sprawl.map((s) => `${s.category} (${s.count})`),
    values: sprawl.map((s) => s.count),
  };
}

/** Case-insensitive search over name/vendor/category/function for the table. */
export function filterItems(items: TechDebtItem[], q: string): TechDebtItem[] {
  const needle = q.trim().toLowerCase();
  if (!needle) return items;
  return items.filter((i) =>
    [i.name, i.vendor, i.category, i.function]
      .filter(Boolean)
      .join(" ")
      .toLowerCase()
      .includes(needle),
  );
}
