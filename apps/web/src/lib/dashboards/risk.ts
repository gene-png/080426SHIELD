/**
 * Client Risk Register dashboard — types + pure transforms (D-035).
 * Mirrors the backend `RiskDashboardResponse`. The 5x5 likelihood x impact
 * matrix is the headline; tier is code-derived.
 */

export interface RiskMatrixCell {
  likelihood: string;
  impact: string;
  tier: string;
  count: number;
}

export interface RiskEntry {
  title: string;
  axis: string | null;
  likelihood: string | null;
  impact: string | null;
  tier: string | null;
  recommended_action: string | null;
}

export interface RiskDashboardData {
  client_id: string;
  released_at: string;
  version: number;
  total_entries: number;
  critical_count: number;
  high_count: number;
  tier_counts: Record<string, number>;
  axis_counts: Record<string, number>;
  action_counts: Record<string, number>;
  matrix: RiskMatrixCell[];
  entries: RiskEntry[];
}

// Display order. Likelihood is shown high→low down the rows so the most severe
// (top-right) corner reads like a standard heat map.
export const LIKELIHOOD_ORDER = [
  "very_low",
  "low",
  "medium",
  "high",
  "very_high",
];
export const IMPACT_ORDER = [
  "negligible",
  "minor",
  "moderate",
  "major",
  "catastrophic",
];
export const TIER_ORDER = ["critical", "high", "medium", "low", "negligible"];

const TIER_COLORS: Record<string, string> = {
  critical: "#ef4444",
  high: "#f59e0b",
  medium: "#eab308",
  low: "#22d3ee",
  negligible: "#10b981",
};

export function tierColor(tier: string): string {
  return TIER_COLORS[tier] ?? "#98a2c4";
}

export function titleCase(s: string): string {
  return s
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

/**
 * Index the flat cell list into `grid[likelihood][impact]` for rendering,
 * rows ordered high→low likelihood (top = very_high).
 */
export function matrixGrid(cells: RiskMatrixCell[]): RiskMatrixCell[][] {
  const byKey = new Map<string, RiskMatrixCell>();
  for (const c of cells) byKey.set(`${c.likelihood}|${c.impact}`, c);
  const rowsHighToLow = [...LIKELIHOOD_ORDER].reverse();
  return rowsHighToLow.map((lk) =>
    IMPACT_ORDER.map(
      (im) =>
        byKey.get(`${lk}|${im}`) ?? {
          likelihood: lk,
          impact: im,
          tier: "negligible",
          count: 0,
        },
    ),
  );
}

export interface MixSlice {
  label: string;
  value: number;
  color: string;
}

/** Tier mix (for the doughnut), in severity order, dropping empty tiers. */
export function tierMix(counts: Record<string, number>): MixSlice[] {
  return TIER_ORDER.filter((t) => (counts[t] ?? 0) > 0).map((t) => ({
    label: titleCase(t),
    value: counts[t],
    color: tierColor(t),
  }));
}
