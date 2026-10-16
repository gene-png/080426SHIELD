/**
 * TD-5 (for #1060): the opt-in AI cost estimate, its copy and its rules.
 *
 * Copy E1 to E7 approved on #736 (6205600298, ruled 6206818759 item 5, with
 * US spelling "license counts" in E3). The rule for "is an estimate" is the
 * web statement of the API's `cost_estimate.is_ai_estimate`.
 */

import type { CapabilityItem } from "./types";
import { noCostItems, sourceItems } from "./components";

/** The run's `purpose`, as `routes/tech_debt.py` starts it. */
export const COST_ESTIMATE_PURPOSE = "tech_debt.cost_estimate";

/** E1, shown when n > 0 on an editable list (Gene's text). */
export function estimatePromptText(n: number): string {
  return n === 1
    ? "This tool has no cost, or none was provided. Enter a cost, or let AI estimate?"
    : `These ${n} tools have no cost, or none was provided. Enter costs, or let AI estimate?`;
}

/** E2, the two buttons. */
export const ENTER_COSTS = "Enter costs";
export const LET_AI_ESTIMATE = "Let AI estimate";

/** E3, shown before the run, beside the button that starts it. */
export const ESTIMATE_DISCLOSURE =
  'AI estimates are based on typical list prices and the license counts in your inventory, not on your contracts. Each one is labelled "AI estimate", and you can overwrite it by editing the cost.';

/** E5, the label on an estimated cost. */
export const AI_ESTIMATE_LABEL = "AI estimate";

/**
 * The source rows whose cost the AI estimated and nobody has overridden: a
 * cost is set and `cost_source` is "ai_estimate". A split bundle's part
 * carries no cost of its own, so it is never one.
 */
export function aiEstimateItems<
  T extends Pick<
    CapabilityItem,
    "parent_item_id" | "annual_cost_usd" | "cost_source"
  >,
>(items: readonly T[]): T[] {
  return sourceItems(items).filter(
    (it) =>
      it.cost_source === "ai_estimate" &&
      it.annual_cost_usd !== null &&
      it.annual_cost_usd !== undefined,
  );
}

/**
 * The rows "Let AI estimate" asks about: the web statement of the API's
 * `cost_estimate.estimate_targets`, TD-10's uncosted source rows minus locked
 * ones. E1 counts these, so its number is the one the run will ask about.
 */
export function estimateTargets<
  T extends Pick<
    CapabilityItem,
    "parent_item_id" | "annual_cost_usd" | "locked"
  >,
>(items: readonly T[]): T[] {
  return noCostItems(items).filter((it) => it.locked !== true);
}

/** E6 beside a total: "{k} costs are AI estimates", or null at 0. */
export function aiEstimateSentence(k: number): string | null {
  if (!Number.isInteger(k) || k <= 0) return null;
  return k === 1 ? "1 cost is an AI estimate" : `${k} costs are AI estimates`;
}

/** What a cost-estimate run stores as its result (`_cost_estimate_run_work`). */
export interface CostEstimateResult {
  asked: number;
  estimated: number;
  declined: number;
  refused: Record<string, number>;
  stray_entries: number;
}

/** A completed run's result, read only when it is a cost-estimate run's. */
export function costEstimateResult(run: {
  purpose: string;
  result: unknown;
}): CostEstimateResult | null {
  if (run.purpose !== COST_ESTIMATE_PURPOSE) return null;
  const r = run.result as Partial<CostEstimateResult> | null;
  if (
    !r ||
    typeof r.asked !== "number" ||
    typeof r.estimated !== "number" ||
    typeof r.declined !== "number" ||
    typeof r.refused !== "object" ||
    r.refused === null
  ) {
    // A result this page cannot read shows no E4 line at all, never
    // "0 estimated"; the warning is the only record of it.
    console.warn("[tech-debt] cost-estimate run result unreadable", run.result);
    return null;
  }
  return r as CostEstimateResult;
}

/**
 * E4: "{a} of {n} tools estimated. {d} the AI could not estimate; they still
 * have no cost." Refusals are added only when non-zero: "{r} estimates were
 * refused ({reasons})."
 */
export function estimateResultLine(r: CostEstimateResult): string {
  const refusedTotal = Object.values(r.refused).reduce((a, b) => a + b, 0);
  const parts = [
    `${r.estimated} of ${r.asked} tools estimated. ${r.declined} the AI could not estimate; they still have no cost.`,
  ];
  if (refusedTotal > 0) {
    const reasons = Object.entries(r.refused)
      .filter(([, n]) => n > 0)
      .map(([reason, n]) => `${reason.replace(/_/g, " ")}: ${n}`)
      .join(", ");
    parts.push(`${refusedTotal} estimates were refused (${reasons}).`);
  }
  return parts.join(" ");
}
