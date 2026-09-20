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
  /**
   * #313. How many entries are counted in `total_entries` but missing from
   * every breakdown.
   *
   * `routes/clients.py::risk_dashboard` publishes `total_entries=len(entries)`
   * while the tier, axis, action and matrix counts are computed over filtered
   * lists -- `[t for t in (...) if t is not None]`. An entry with no tier is
   * therefore in the headline and in none of the breakdowns, and the two
   * disagree with nothing saying why.
   *
   * OPTIONAL, and the optionality is the disclosure. A register serialized
   * before this field existed carries no count, which is "nobody looked" and
   * not "nothing was withheld". `undefined` renders as NOT RECORDED; a zero
   * renders as silence. Collapsing them would manufacture a positive
   * certificate out of absence, which is the #244 shape.
   */
  entries_without_tier?: number;
  /**
   * #313. The axis and action breakdowns filter INDEPENDENTLY of the tier one,
   * so one count cannot explain all three. An entry can carry a valid tier and
   * an unresolvable axis, and is then in the headline, in the matrix, in the
   * tier counts, and absent from `axis_counts` -- which the tier count reports
   * as zero.
   */
  entries_without_axis?: number;
  entries_without_action?: number;
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
