import type { AiSource } from "@/lib/aiSource/types";

/**
 * Client NIST CSF 2.0 dashboard — types + pure transforms.
 * Mirrors the backend `CsfDashboardResponse` (apps/api/app/schemas/clients.py).
 *
 * CSF was the only service without a client dashboard: `dashboardPathFor`
 * returned null for `nist_csf`, so a client could see a CSF gap count on their
 * home page and had no way to open the results.
 */

import { targetSourceNote } from "@/lib/assessment-targets";

export interface CsfFunction {
  code: string;
  name: string;
  subcategory_count: number;
  answered_count: number;
  coverage_pct: number;
  current_tier: number | null;
  current_pct: number | null;
  /** "Unscored" when the function has no answers — see `_csf_function_label`. */
  current_label: string;
  target_pct: number | null;
  gap_pct: number;
  gap_count: number;
  weakest: string[];
}

export interface CsfGap {
  code: string;
  name: string;
  function: string;
  function_name: string;
  current_tier: number;
  target_tier: number;
  gap_size: number;
  priority_score: number;
}

export interface CsfDashboardData {
  /** #646: which mode drafted the AI suggestions, as the API states it. */
  ai_source: AiSource;
  service_id: string;
  service_title: string;
  released_at: string;
  released?: boolean;
  deliverable_version: number;

  overall_label: string;
  current_tier: number | null;
  current_pct: number | null;
  coverage_pct: number;

  target_tier: number;
  target_label: string;
  target_pct: number;
  /**
   * Not two values (#184): "client", "default", "client_out_of_range",
   * "client_unparseable", and since #85 "client_below_floor". The last three
   * mean the client DID choose and the choice could not be used — a different
   * fact from choosing nothing, and the only one a consultant can act on by
   * re-asking them.
   *
   * Rendered, not just carried — see `targetIsAssumed` and `targetFaultNote`.
   */
  target_tier_source: string;
  /**
   * The ZT twin of this field, and the same disclosure — see
   * `dashboards/zt.ts` and `renderedAgainstNote`. Both services get it in
   * the same commit: fixing one and not the other is the half-sweep
   * #75/#79 record making a card worse than the defect it replaced.
   */
  target_frozen_at: string | null;

  total_gap_count: number;
  largest_gap_function: string | null;
  largest_gap_pct: number;

  functions: CsfFunction[];
  /** Ranked and TRUNCATED. `total_gap_count` is the real total. */
  top_gaps: CsfGap[];
  /**
   * #852: answers kept on a subcategory the catalog no longer has (ID.AM-09),
   * in no figure above, with the API's approved sentence: the one the
   * released document carries (`csf/retired.py`).
   */
  retired_answers?: number;
  retired_answers_note?: string | null;
}

/* No `radarData` here, deliberately. ZT ships one because `ZtCharts` renders a
   radar; this dashboard has no chart, so an exported transform with no caller
   would be dead code that its own tests then "cover" — 22% of a suite proving
   nothing about the product. Add it back with the chart, not before. */

/** Functions ordered by the largest current→target gap first (focus ordering). */
export function functionsByGap(functions: CsfFunction[]): CsfFunction[] {
  return [...functions].sort((a, b) => b.gap_pct - a.gap_pct);
}

/**
 * How many prioritized gaps exist beyond the ones shown.
 *
 * #75 is open because the ZT exporter renders a 20-item slice with the true
 * total nowhere on the page, so a client reads 20 of 37 remediation items with
 * no statement that anything was omitted. This dashboard must not repeat that,
 * so the shortfall is computed here rather than left to each caller to
 * remember — and it is clamped at 0 so a short list never reads as negative.
 */
export function hiddenGapCount(data: CsfDashboardData): number {
  return Math.max(0, data.total_gap_count - data.top_gaps.length);
}

/**
 * True when the target tier is the engine default rather than the client's own
 * choice at intake.
 *
 * Surfaced because of #73: the ZT exporter has computed gaps against a
 * hardcoded 3 for the life of the repo while the client had chosen 4, so a
 * delivered document listed a different gap set than the consultant approved.
 * A number nobody chose must be visibly distinguishable from one they did.
 */
export function targetIsAssumed(data: CsfDashboardData): boolean {
  return data.target_tier_source !== "client";
}

/**
 * WHY the target is assumed, in the client's own terms, or null when it is not.
 *
 * `targetIsAssumed` above is a boolean and stays one — it fails safe for any
 * unknown source. But a boolean cannot distinguish "you chose nothing" from
 * "your choice could not be used", and collapsing the two prints the first
 * sentence over the second: the client is told they made no choice when they
 * made one that was discarded. That is a lie in their own words, and it is the
 * reason the ZT twin's `targetFault` exists.
 *
 * Mirrored from `dashboards/zt.ts::targetFault` rather than worded again, so
 * two services cannot describe one fault differently.
 *
 * An unrecognised value still says SOMETHING true rather than falling through
 * to the "chose nothing" copy: the API is the source of this string.
 *
 * #783 / #422: the words are the `tier` rows of `TARGET_SOURCE_NOTES` in
 * `lib/assessment-targets.ts`, the ONE table. The client's documents state the
 * same rows from the api's copy (`assessment_targets.py::target_source_sentence`),
 * which the api's `test_target_floor_parity.py` asserts equal to that table.
 * Reword the table, never here.
 */
export function targetFaultNote(source: string): string | null {
  return targetSourceNote("tier", source);
}
