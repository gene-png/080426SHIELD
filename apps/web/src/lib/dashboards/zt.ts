/**
 * Client Zero Trust maturity dashboard — types + pure transforms (D-035).
 * Mirrors the backend `ZtDashboardResponse` (apps/api/app/schemas/clients.py).
 */

export interface ZtPillar {
  code: string;
  name: string;
  capability_count: number;
  answered_count: number;
  current_pct: number | null;
  current_label: string;
  target_pct: number | null;
  target_label: string;
  gap_pct: number;
  weakest: string[];
}

export interface ZtDashboardData {
  service_id: string;
  service_title: string;
  released_at: string;
  released?: boolean;
  deliverable_version: number;
  framework: string;
  framework_label: string;
  current_label: string;
  current_pct: number | null;
  target_label: string;
  target_pct: number | null;

  target_stage: number;
  /** See `targetNote` — rendered, not just carried. */
  target_stage_source: string;
  /**
   * How many capabilities the engagement stage actually decided. Zero means
   * every capability carried its own target and the intake choice contributed
   * nothing to the percentage shown.
   */
  engagement_target_capability_count: number;

  /**
   * Every gap the engine found, not a rendered subset.
   *
   * Close to the released document's figure and NOT guaranteed equal to it:
   * the document is frozen at finalize, this is recomputed per request against
   * a target that stays writable after release (#209).
   */
  total_gap_count: number;

  largest_gap_pillar: string | null;
  largest_gap_pct: number;
  pillars: ZtPillar[];
}

export interface RadarData {
  labels: string[];
  current: number[];
  target: number[];
}

/** Current-vs-target maturity % per pillar for the radar chart. */
export function radarData(pillars: ZtPillar[]): RadarData {
  return {
    labels: pillars.map((p) => p.name),
    current: pillars.map((p) => p.current_pct ?? 0),
    target: pillars.map((p) => p.target_pct ?? 0),
  };
}

/** Pillars ordered by the largest current→target gap first (focus ordering). */
export function pillarsByGap(pillars: ZtPillar[]): ZtPillar[] {
  return [...pillars].sort((a, b) => b.gap_pct - a.gap_pct);
}

/**
 * The sub-label under the target KPI, naming the target's provenance.
 *
 * Every source gets its own sentence, and the two FAILURE sources are never
 * collapsed into "no stage chosen at intake": that would be a lie in the
 * client's own words -- they DID choose, and the choice could not be used, a
 * fact a consultant can act on by re-asking. #125 went to some trouble to keep
 * those apart on the way here. An unrecognised value falls through to the
 * assumed-target wording rather than being asserted as a client choice,
 * because #124's whole failure mode was a fallback that read like a decision.
 *
 * A fully-overridden target changes the SUBJECT of the sentence but never
 * suppresses a fault -- see below.
 */
export function targetNote(data: ZtDashboardData): string {
  const fault = targetFault(data.target_stage_source);

  // The engagement target decided nothing here: every capability carried its
  // own. Captioning this percentage "your target, chosen at intake" would name
  // a source that contributed none of it -- #124's defect facing the other
  // way, a label that does not describe the number beside it.
  //
  // The fault is still APPENDED rather than dropped. An earlier draft returned
  // early here, which silently swallowed `client_out_of_range` and
  // `client_unparseable` for any assessment that happened to set every per-row
  // target -- so the one state a consultant can act on became the one state
  // nothing rendered, in the function written to keep those states apart.
  if (data.engagement_target_capability_count === 0) {
    const base = "Per-capability targets from your assessment";
    // Only a FAILED client choice is appended. "default" means the client
    // chose nothing, which is not a fault and not actionable — and when the
    // engagement stage decided no capability either, saying so is noise about
    // a value that did not reach the page.
    return isChoiceFailure(data.target_stage_source)
      ? `${base} — ${fault}`
      : base;
  }

  return fault === null
    ? "Your target, chosen at intake"
    : `Default target — ${fault}`;
}

/**
 * True when the client made a choice that could not be used — as opposed to
 * having made none. `resolve_target_stage` keeps those apart because only the
 * first is answerable by re-asking the client, and flattening them here would
 * throw that away one layer from the reader.
 *
 * An UNKNOWN source counts as a failure: a value this build does not recognise
 * is not evidence that the client chose nothing.
 */
function isChoiceFailure(source: string): boolean {
  return source !== "client" && source !== "default";
}

/**
 * Why the client's stored stage could not be used, or null if it was.
 *
 * Split out so the fully-overridden branch above and the ordinary one report
 * the same fault in the same words: two copies of this mapping would be two
 * places for the wording to drift, and the drift would be invisible because
 * each branch is reached by a different fixture.
 */
function targetFault(source: string): string | null {
  switch (source) {
    case "client":
      return null;
    case "default":
      return "no stage chosen at intake";
    case "client_out_of_range":
      return "the stage on file is not one this framework has";
    case "client_unparseable":
      return "the stage on file could not be read";
    default:
      return "the stage on file was not usable";
  }
}
