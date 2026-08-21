/**
 * Client ATT&CK coverage dashboard — types + pure transforms (D-035).
 *
 * These mirror the backend `AttackDashboardResponse`
 * (apps/api/app/schemas/clients.py) and derive the KPI / chart / D-P-R / matrix
 * values the dark dashboard renders. Kept pure (no React, no Chart.js) so they
 * are unit-testable in isolation.
 */

export type CoverageStatus = "covered" | "partial" | "gap" | "not_applicable";

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
  coverage_pct: number;
}

export interface DashTechnique {
  code: string;
  name: string;
  tactic_name: string;
  status: CoverageStatus;
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
  coverage_pct: number;
  by_tactic: DashTactic[];
}

export interface AttackDashboardData {
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
}

/**
 * Detect / Prevent / Respond posture: a leg counts for an evaluated technique
 * when that technique lists at least one tool for it. SHIELD stores explicit
 * tool lists, so this is a direct non-empty check (no string heuristics).
 */
export function dprCoverage(techniques: DashTechnique[]): DprCoverage {
  const total = techniques.length;
  const detect = techniques.filter((t) => t.detection_tools.length > 0).length;
  const prevent = techniques.filter(
    (t) => t.prevention_tools.length > 0,
  ).length;
  const respond = techniques.filter((t) => t.response_tools.length > 0).length;
  return {
    total,
    detect: { n: detect, pct: pctOf(detect, total) },
    prevent: { n: prevent, pct: pctOf(prevent, total) },
    respond: { n: respond, pct: pctOf(respond, total) },
  };
}

/** Uncovered techniques (the "what you're blind to today" cards). */
export function blindSpots(techniques: DashTechnique[]): DashTechnique[] {
  return techniques.filter((t) => t.status === "gap");
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
