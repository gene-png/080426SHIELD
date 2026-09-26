/**
 * Client ATT&CK coverage dashboard — types + pure transforms (D-035).
 *
 * These mirror the backend `AttackDashboardResponse`
 * (apps/api/app/schemas/clients.py) and derive the KPI / chart / D-P-R / matrix
 * values the dark dashboard renders. Kept pure (no React, no Chart.js) so they
 * are unit-testable in isolation.
 */

/** Every status the API can store (#554). The two new ones are not WRITABLE
 *  yet, but every surface must be able to render them first. */
export type CoverageStatus =
  | "covered"
  | "partial"
  | "gap"
  | "not_applicable"
  | "outside_control_surface"
  | "unable_to_determine";

export interface DashTactic {
  tactic_id: string;
  tactic_name: string;
  covered: number;
  partial: number;
  gap: number;
  not_applicable: number;
  unscored: number;
  /** #102: status assigned, supporting citation unconfirmed, withheld from the %. */
  pending_review?: number;
  /** #554: outside the assessed denominator; always beside the percentage. */
  outside_control_surface: number;
  unable_to_determine: number;
  coverage_pct: number;
}

export interface DashTechnique {
  code: string;
  name: string;
  tactic_name: string;
  status: CoverageStatus;
  /**
   * #102: the status is assigned but its supporting citation is unconfirmed, so
   * the rollup withholds it. Carried beside `status`, never over it.
   */
  pending_review?: boolean;
  /**
   * #620 round 2 (D-094): a parent whose status is computed from its
   * sub-techniques. The API sends no tools or rationale for it, and the
   * Detect / Prevent / Respond triad leaves it out, so each technique is
   * counted once, through its sub-techniques. Required: set by the API from
   * the catalog's parent links. ABSENT for an assessment approved before #620
   * (Gene's condition, D-094), which renders exactly as it was delivered.
   */
  computed_parent?: boolean;
  /** How many sub-techniques it is computed from; 0 when it is not a computed
   *  parent. Set by the API with `computed_parent`, from the same links. */
  sub_technique_count?: number;
  detection_tools: string[];
  prevention_tools: string[];
  response_tools: string[];
  rationale: string | null;
}

export interface DashRollup {
  total_evaluated: number;
  covered: number;
  partial: number;
  gap: number;
  not_applicable: number;
  /**
   * #102. Techniques whose status is withheld from `coverage_pct` because their
   * supporting citation is unconfirmed. Withholding narrows the DENOMINATOR, so
   * the percentage is not self-describing and this count must be rendered
   * beside it — the same rule the released PDF follows.
   */
  pending_review?: number;
  /** #554: outside the assessed denominator; always beside the percentage. */
  outside_control_surface: number;
  unable_to_determine: number;
  coverage_pct: number;
  by_tactic: DashTactic[];
}

export interface AttackDashboardData {
  /** True for an assessment approved under D-094's rules for computed parents
   *  (#620). Absent for one approved before, which renders as delivered. */
  parents_computed?: boolean;
  service_id: string;
  service_title: string;
  released_at: string;
  deliverable_version: number;
  rollup: DashRollup;
  techniques: DashTechnique[];
}

export interface Kpi {
  n: number;
  pct: number;
}

export interface DashboardKpis {
  evaluated: number;
  covered: Kpi;
  partial: Kpi;
  blindSpots: Kpi; // uncovered / gap
}

function pctOf(n: number, total: number): number {
  return total === 0 ? 0 : Math.round((n / total) * 100);
}

/** Four headline KPI cards: evaluated total + covered/partial/blind-spot mix. */
export function kpis(data: AttackDashboardData): DashboardKpis {
  const evaluated = data.rollup.total_evaluated;
  return {
    evaluated,
    covered: {
      n: data.rollup.covered,
      pct: pctOf(data.rollup.covered, evaluated),
    },
    partial: {
      n: data.rollup.partial,
      pct: pctOf(data.rollup.partial, evaluated),
    },
    blindSpots: { n: data.rollup.gap, pct: pctOf(data.rollup.gap, evaluated) },
  };
}

export interface DprLeg {
  n: number;
  pct: number;
}

export interface DprCoverage {
  detect: DprLeg;
  prevent: DprLeg;
  respond: DprLeg;
  total: number;
  /** Rows the population left out, from the SAME filter, so the page can say
   *  what the percentages are over (#620 round 3). */
  excluded: { parents: number; pending: number };
}

/**
 * Detect / Prevent / Respond posture: a leg counts for an evaluated technique
 * when that technique lists at least one tool for it. SHIELD stores explicit
 * tool lists, so this is a direct non-empty check (no string heuristics).
 *
 * Techniques the rollup is WITHHOLDING are excluded from both the numerator and
 * the denominator (#102). The tools on a withheld row are precisely the
 * unconfirmed ones — the resolver applies a rescued citation and flags it — so
 * counting them made a run whose every citation was inferred report "Detect
 * 100%" on the same page whose rollup said zero covered.
 *
 * Out of BOTH sides, like `unscored` and for the same reason: it is a claim not
 * being made, not a claim of absence. Scoring it as a zero would understate the
 * posture rather than decline to state it.
 *
 * Only ASSESSED rows (covered, partial, gap) are in the triad, as in the KPI
 * row and `coverage_pct`. The two #554 statuses are outside it -- nobody
 * verified the technique, or the client's controls do not reach it -- and
 * their counts are rendered beside the triad instead. N/A is outside it too:
 * Gene's decision, 2026-09-25 (D-092), so the triad and the KPI row divide by
 * the same population.
 *
 * A COPY of `coverage.ASSESSED` in `apps/api/app/attack/coverage.py`, which
 * points here -- change both.
 */
const ASSESSED: ReadonlySet<CoverageStatus> = new Set([
  "covered",
  "partial",
  "gap",
]);

export function dprCoverage(techniques: DashTechnique[]): DprCoverage {
  // BOTH exclusions (#620 and #621, resolved together): the population is
  // assessed rows only (covered, partial, gap -- #621, Gene's N/A decision),
  // minus rows pending review, minus computed parents, which carry no tools of
  // their own and are counted through their sub-techniques (#620, option (b)).
  const claimable = techniques.filter(
    (t) => !t.pending_review && !t.computed_parent && ASSESSED.has(t.status),
  );
  // Each excluded row is counted once, under the first reason that excludes
  // it: a parent is out as a parent whether or not it is also pending. Rows
  // outside ASSESSED are stated beside the triad by #621's sentence instead.
  const parents = techniques.filter((t) => t.computed_parent).length;
  const pending = techniques.filter(
    (t) => !t.computed_parent && t.pending_review,
  ).length;
  const total = claimable.length;
  const detect = claimable.filter((t) => t.detection_tools.length > 0).length;
  const prevent = claimable.filter((t) => t.prevention_tools.length > 0).length;
  const respond = claimable.filter((t) => t.response_tools.length > 0).length;
  return {
    total,
    excluded: { parents, pending },
    detect: { n: detect, pct: pctOf(detect, total) },
    prevent: { n: prevent, pct: pctOf(prevent, total) },
    respond: { n: respond, pct: pctOf(respond, total) },
  };
}

/** Uncovered techniques (the "what you're blind to today" cards). */
export function blindSpots(techniques: DashTechnique[]): DashTechnique[] {
  // Through sub-techniques, like the triad (#620 round 3): a parent with
  // sub-techniques has no tools of its own, and its gap is its children's.
  return techniques.filter((t) => t.status === "gap" && !t.computed_parent);
}

/** The sentence beside the triad naming what its percentages leave out. */
export function triadPopulationText(d: DprCoverage): string {
  const out: string[] = [];
  if (d.excluded.parents > 0) {
    out.push(
      `${d.excluded.parents} parent technique${d.excluded.parents === 1 ? "" : "s"}, counted through ${d.excluded.parents === 1 ? "its" : "their"} sub-techniques`,
    );
  }
  if (d.excluded.pending > 0) out.push(`${d.excluded.pending} pending review`);
  const base = `Over ${d.total} technique${d.total === 1 ? "" : "s"}.`;
  return out.length === 0
    ? base
    : `${base} Not counted here: ${out.join(", and ")}.`;
}

export interface TacticBar {
  labels: string[];
  covered: number[];
  partial: number[];
  gap: number[];
}

/**
 * Stacked-bar data per tactic, keeping only tactics that have at least one
 * addressable (covered/partial/gap) technique, in the rollup's tactic order.
 */
export function tacticBar(byTactic: DashTactic[]): TacticBar {
  const rows = byTactic.filter((t) => t.covered + t.partial + t.gap > 0);
  return {
    labels: rows.map((t) => t.tactic_name),
    covered: rows.map((t) => t.covered),
    partial: rows.map((t) => t.partial),
    gap: rows.map((t) => t.gap),
  };
}

/** Overall covered/partial/uncovered counts for the coverage-mix donut. */
export function coverageMix(rollup: DashRollup): {
  covered: number;
  partial: number;
  gap: number;
} {
  return { covered: rollup.covered, partial: rollup.partial, gap: rollup.gap };
}

export interface MatrixFilter {
  q: string;
  tactic: string; // "" = all
  status: string; // "" = all
}

/** Search (id/name/tool) + tactic + coverage filtering for the matrix table. */
export function filterTechniques(
  techniques: DashTechnique[],
  filter: MatrixFilter,
): DashTechnique[] {
  const q = filter.q.trim().toLowerCase();
  return techniques.filter((t) => {
    if (filter.tactic && t.tactic_name !== filter.tactic) return false;
    if (filter.status && t.status !== filter.status) return false;
    if (q) {
      const hay = [
        t.code,
        t.name,
        t.tactic_name,
        ...t.detection_tools,
        ...t.prevention_tools,
        ...t.response_tools,
      ]
        .join(" ")
        .toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

/** Distinct tactic names present, for the filter dropdown. */
export function tacticOptions(techniques: DashTechnique[]): string[] {
  return [...new Set(techniques.map((t) => t.tactic_name))].sort();
}
