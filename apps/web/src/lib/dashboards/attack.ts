import type { AiSource } from "@/lib/aiSource/types";

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
  /** #554: outside the assessed denominator; always beside the percentage.
   *  Absent for an assessment approved before #620 (option (a)). */
  outside_control_surface?: number;
  unable_to_determine?: number;
  coverage_pct: number;
  /** #489: false where nothing is Covered, Partial, Gap or pending review, so
   *  `coverage_pct` (0.0 there) is shown as "not measured", as the deliverable
   *  says. Decided by the API with the exporter's own rule; never re-derived. */
  coverage_measured: boolean;
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
  /**
   * #554 R1: why a Partial technique is partial, in the client's words
   * (`app/attack/partial_reasons.py`). Present on a Partial row only.
   */
  partial_reason?: { label: string; sentence: string };
  /**
   * #554 R3: which of Detect / Prevent / Respond are in place, in the client's
   * words (`app/attack/computed.py::IN_PLACE_TEXT`), and the approved line.
   * Present on a row whose status was computed; absent before R3.
   */
  in_place?: {
    /** The client's words, for display only. */
    detect: string;
    prevent: string;
    respond: string;
    line: string;
    cannot_be_prevented: boolean;
    /** The machine values (`app/attack/computed.py::InPlace`). Logic reads
     *  these, never the words above. */
    state: {
      detect: InPlaceState;
      prevent: InPlaceState;
      respond: InPlaceState;
    };
  };
  detection_tools: string[];
  prevention_tools: string[];
  response_tools: string[];
  rationale: string | null;
}

/** #554 R3: one capability's machine value. */
export type InPlaceState =
  "in_place" | "not_in_place" | "awaiting_review" | "cannot_be_prevented";

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
  /** #554: outside the assessed denominator; always beside the percentage.
   *  Absent for an assessment approved before #620 (option (a)). */
  outside_control_surface?: number;
  unable_to_determine?: number;
  coverage_pct: number;
  /** #489: false where nothing is Covered, Partial, Gap or pending review, so
   *  `coverage_pct` (0.0 there) is shown as "not measured", as the deliverable
   *  says. Decided by the API with the exporter's own rule; never re-derived. */
  coverage_measured: boolean;
  by_tactic: DashTactic[];
}

export interface AttackDashboardData {
  /** #646: which mode drafted the AI suggestions, as the API states it. */
  ai_source: AiSource;
  /** True for an assessment approved under D-094's rules for computed parents
   *  (#620). Absent for one approved before, which renders as delivered. */
  parents_computed?: boolean;
  service_id: string;
  service_title: string;
  released_at: string;
  deliverable_version: number;
  rollup: DashRollup;
  techniques: DashTechnique[];
  /**
   * #686 (D-105): cited tool -> "planned_retirement" | "unknown", from the
   * client's CURRENT Tech Debt consolidation plan; a tool absent here is not
   * retiring. Absent (with `retirement_notes`) when the client has no plan.
   */
  tool_retirement?: Record<string, string>;
  /** The deliverable's own count sentences, each only when non-zero. */
  retirement_notes?: string[];
  /**
   * #554 R1: the "Partial coverage, by reason" table, the deliverable's own
   * rows (`partial_reason_counts`), adding up to `rollup.partial`. Absent when
   * there is no Partial.
   */
  partial_reasons?: { label: string; sentence: string; count: number }[];
  /** #554 R3 (Q4): the deliverable's sentence beside the percentage. Absent
   *  before R3 and when nothing awaits review. */
  awaiting_review_sentence?: string;
  /** #554 R3: true when statuses are computed from Detect / Prevent / Respond.
   *  Absent before R3. */
  statuses_computed?: boolean;
  /** #801: the coverage figure after planned changes (with the current plan)
   *  and its counts, as the API words them. Absent where there is nothing to
   *  recount: before R3, or for a client with no consolidation plan. */
  after_planned_changes?: string[];
}

/**
 * #554 R3: the "Techniques that cannot be prevented" section, approved on #554
 * (21:55Z). COPIED from `apps/api/app/attack/computed.py`; change both.
 */
export const CANNOT_BE_PREVENTED_HEADING =
  "Techniques that cannot be prevented";
export const CANNOT_BE_PREVENTED_SENTENCE =
  "MITRE ATT&CK lists no preventive control for these techniques, so they are assessed on detection and response. A technique here is Covered when it is both detected and responded to.";

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
    // The rollup's count, as on main, for every rule set (#620 round 5): every
    // KPI describes the same population as `coverage_pct`, so the three sum to
    // 100%. Where the blind-spot LIST differs (rule 2 lists gaps through
    // sub-techniques), `blindSpotReconciliation` says so at the list.
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
  /** #554 R3, the advisor's ruling (a): Prevent's own denominator, which leaves
   *  out the techniques that cannot be prevented. Equals `total` otherwise. */
  preventTotal: number;
  /** Rows the population left out, from the SAME filter, so the page can say
   *  what the percentages are over (#620 round 3). */
  excluded: {
    parents: number;
    pending: number;
    /** #621 round 5: rows outside the ASSESSED population, by status. Only
     *  under #620's rules, where the triad drops them; zero under rule 1. */
    notApplicable: number;
    notVerified: number;
    outside: number;
    /** #554 R3: left out of Prevent's denominator only. */
    cannotBePrevented: number;
  };
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

/**
 * #554 R3: whether one leg is present on a technique. On a row whose status was
 * computed it is the API's "in place" -- a listed tool still awaiting review is
 * NOT a leg, and neither is "cannot be prevented" -- so the triad agrees with
 * the status beside it. Before R3 it is a non-empty tool list, as delivered.
 */
export function legOn(
  t: DashTechnique,
  leg: "detect" | "prevent" | "respond",
): boolean {
  if (t.in_place) return t.in_place.state[leg] === "in_place";
  const tools = {
    detect: t.detection_tools,
    prevent: t.prevention_tools,
    respond: t.response_tools,
  }[leg];
  return tools.length > 0;
}

export function dprCoverage(
  techniques: DashTechnique[],
  /** `data.parents_computed === true`: the assessment is under #620's rules.
   *  #621's ASSESSED-only population applies there alone (option (a)); one
   *  approved before #620 keeps the triad it was delivered with. */
  newRules = false,
): DprCoverage {
  // A computed parent is out too (#620 round 2, option (b), pending Gene's
  // confirmation): it carries no tools of its own, so counting it would add a
  // zero-leg row per parent beside the children it is computed from.
  const claimable = techniques.filter(
    (t) =>
      !t.pending_review &&
      !t.computed_parent &&
      (!newRules || ASSESSED.has(t.status)),
  );
  // Each excluded row is counted once, under the first reason that excludes
  // it: a parent is out as a parent whether or not it is also pending.
  const parents = techniques.filter((t) => t.computed_parent).length;
  const pending = techniques.filter(
    (t) => !t.computed_parent && t.pending_review,
  ).length;
  // Then the ASSESSED filter, per status, so the sentence can name what it
  // dropped: without these an N/A row left the denominator in silence and
  // raised every percentage (#621 round 5).
  const notAssessed = (status: CoverageStatus): number =>
    newRules
      ? techniques.filter(
          (t) => !t.computed_parent && !t.pending_review && t.status === status,
        ).length
      : 0;
  const total = claimable.length;
  const detect = claimable.filter((t) => legOn(t, "detect")).length;
  // #554 R3, ruling (a): a technique that cannot be prevented is not in
  // Prevent's denominator, and the population sentence says so.
  const preventable = claimable.filter((t) => !t.in_place?.cannot_be_prevented);
  const prevent = preventable.filter((t) => legOn(t, "prevent")).length;
  const respond = claimable.filter((t) => legOn(t, "respond")).length;
  return {
    total,
    excluded: {
      parents,
      pending,
      notApplicable: notAssessed("not_applicable"),
      notVerified: notAssessed("unable_to_determine"),
      outside: notAssessed("outside_control_surface"),
      cannotBePrevented: total - preventable.length,
    },
    preventTotal: preventable.length,
    detect: { n: detect, pct: pctOf(detect, total) },
    prevent: { n: prevent, pct: pctOf(prevent, preventable.length) },
    respond: { n: respond, pct: pctOf(respond, total) },
  };
}

/** Uncovered techniques (the "what you're blind to today" cards). */
export function blindSpots(techniques: DashTechnique[]): DashTechnique[] {
  // Through sub-techniques, like the triad (#620 round 3): a parent with
  // sub-techniques has no tools of its own, and its gap is its children's.
  return techniques.filter((t) => t.status === "gap" && !t.computed_parent);
}

/**
 * #620 round 5: the sentence that reconciles the Blind spots KPI (the rollup's
 * gaps, parents included) with the list (gaps through sub-techniques), or null
 * when they agree. Only under D-094's rules, where the list excludes parents;
 * the difference is exactly the gap parents, since a gap is never withheld.
 */
export function blindSpotReconciliation(
  data: AttackDashboardData,
): string | null {
  if (data.parents_computed !== true) return null;
  const listed = blindSpots(data.techniques).length;
  const parents = data.rollup.gap - listed;
  if (parents <= 0) return null;
  const tail =
    parents === 1
      ? "1 parent technique whose gap is listed through its sub-techniques"
      : `${parents} parent techniques whose gaps are listed through their sub-techniques`;
  return `The Blind spots figure above counts ${data.rollup.gap}: the ${listed} listed here, and ${tail}.`;
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
  if (d.excluded.notApplicable > 0) out.push(`${d.excluded.notApplicable} N/A`);
  if (d.excluded.notVerified > 0)
    out.push(`${d.excluded.notVerified} Not verified`);
  if (d.excluded.outside > 0)
    out.push(`${d.excluded.outside} outside the control surface`);
  const base = `Over ${d.total} technique${d.total === 1 ? "" : "s"}.`;
  const text =
    out.length === 0
      ? base
      : `${base} Not counted here: ${out.join(", and ")}.`;
  // #554 R3, ruling (a): Prevent's own denominator, named.
  const np = d.excluded.cannotBePrevented;
  return np === 0
    ? text
    : `${text} Prevent is over ${d.preventTotal} technique${d.preventTotal === 1 ? "" : "s"}: ` +
        (np === 1
          ? "1 that cannot be prevented is not counted for it."
          : `${np} that cannot be prevented are not counted for it.`);
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
