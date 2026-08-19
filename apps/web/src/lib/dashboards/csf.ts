/**
 * Client NIST CSF 2.0 dashboard — types + pure transforms.
 * Mirrors the backend `CsfDashboardResponse` (apps/api/app/schemas/clients.py).
 *
 * CSF was the only service without a client dashboard: `dashboardPathFor`
 * returned null for `nist_csf`, so a client could see a CSF gap count on their
 * home page and had no way to open the results.
 */

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
   * "client" when the target came from the intake choice, "default" when the
   * client never set one. Rendered, not just carried — see `targetIsAssumed`.
   */
  target_tier_source: string;

  total_gap_count: number;
  largest_gap_function: string | null;
  largest_gap_pct: number;

  functions: CsfFunction[];
  /** Ranked and TRUNCATED. `total_gap_count` is the real total. */
  top_gaps: CsfGap[];
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
