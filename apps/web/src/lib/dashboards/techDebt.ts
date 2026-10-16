import type { AiSource } from "@/lib/aiSource/types";
import { AI_ESTIMATE_LABEL } from "@/lib/tech_debt/costEstimate";

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
  /**
   * for #929: the bundle that carries this row's cost when the row is a named
   * part of a split bundle. "" when that bundle's name is blank (still a part);
   * null for a row that is not a part.
   */
  bundle: string | null;
  /** TD-5 (for #1060): the cost is an AI estimate, labelled (copy E5). */
  ai_estimate: boolean;
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
  /**
   * for #1044: false when a counted (cut) row in this category has no usable
   * cost, so `savings_usd` is a floor. Only `true` reads as exact: a missing
   * flag (an API older than the field) is unconfirmed, never confirmed.
   */
  savings_cost_known: boolean;
  items: TechDebtItem[];
}

export interface TechDebtDashboardData {
  /** #646: which mode drafted the AI suggestions, as the API states it. */
  ai_source: AiSource;
  service_id: string;
  service_title: string;
  released_at: string;
  deliverable_version: number;
  /** for #835: source items only; a split bundle's parts are not applications. */
  total_applications: number;
  /** How many of `items` are named parts of a split bundle. */
  bundle_part_count: number;
  annual_spend_usd: number;
  identified_savings_usd: number;
  savings_cost_known: boolean;
  // #126. Three states, not a boolean: "complete" (every row accounted for and
  // costed), "partial" (something is known missing), "unknown" (completeness
  // was never recorded for this list -- pre-0036, or never cut by an
  // extraction). A bool cannot carry the third, and folding it into "complete"
  // is what let the spend figure claim totality it had no basis for.
  spend_completeness: "complete" | "partial" | "unknown";
  // NULL source_rows_total means the upload was never reconciled -- distinct
  // from zero rows received.
  source_rows_total: number | null;
  included_count: number;
  excluded_count: number;
  /**
   * #177/#193: true only when the extraction attributed every item to one
   * uploaded row, so `excluded_count` is the count. False makes it a FLOOR:
   * the true number of excluded rows is unknown, and may be higher.
   */
  excluded_count_exact: boolean;
  /**
   * TD-10 (for #1048): source items (not a split bundle's parts) with no
   * recorded cost, which `annual_spend_usd` leaves out. A recorded $0 is a
   * cost and is not counted.
   */
  no_cost_count: number;
  /**
   * TD-5 (for #1060): source items whose cost is an AI estimate, which
   * `annual_spend_usd` INCLUDES. Any one makes spend "partial" (E7).
   */
  ai_estimate_count: number;
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

/**
 * The cost cell for one inventory or redundancy row (for #929). A bundle's
 * part has no cost of its own: its bundle holds the licence value and the
 * spend figure counts it there, so the cell says where the cost is rather than
 * "—", which reads as unknown. A cost stored on a part before #927 refused one
 * is not shown, because spend does not count it. Only a STRING marks a part:
 * "" is a part whose bundle has a blank name, so this never tests truthiness,
 * and a missing key (an API older than this field) is not a part, so it never
 * tests `!== null` either, which would print "Included in undefined".
 */
export function itemCost(it: TechDebtItem): string {
  if (typeof it.bundle === "string") {
    return it.bundle === ""
      ? "Included in its bundle"
      : `Included in ${it.bundle}`;
  }
  const cost = usdCompact(it.annual_cost_usd);
  // TD-5 (for #1060), copy E5: an estimate is labelled wherever it appears.
  return it.ai_estimate === true ? `${cost} (${AI_ESTIMATE_LABEL})` : cost;
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
