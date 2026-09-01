/** Wire types mirroring apps/api/app/schemas/attack.py. */

export type CoverageStatus = "covered" | "partial" | "gap" | "not_applicable";
export type AttackAssessmentStatus =
  "draft" | "approved" | "released" | "discarded";

export interface CatalogTactic {
  id: string;
  shortname: string;
  name: string;
  description: string;
}

export interface CatalogTechnique {
  id: string;
  name: string;
  tactics: string[];
  parent_id: string | null;
  is_sub_technique: boolean;
}

export interface CatalogCoverageDefinition {
  status: CoverageStatus;
  short_label: string;
  description: string;
}

export interface AttackCatalog {
  tactics: CatalogTactic[];
  techniques: CatalogTechnique[];
  coverage_definitions: CatalogCoverageDefinition[];
  total_techniques: number;
  total_sub_techniques: number;
}

export interface AttackCoverageRow {
  id: string;
  assessment_id: string;
  technique_code: string;
  status: CoverageStatus | null;
  notes: string | null;
  evidence_artifact_id: string | null;
  locked?: boolean;
  detection_tools?: string[] | null;
  prevention_tools?: string[] | null;
  response_tools?: string[] | null;
  rationale?: string | null;
  answered_by: string | null;
  answered_at: string | null;
  // #101. Citations the resolver had to INFER rather than match, and whether a
  // human has since vouched for each. `null` is NOT the same as `[]`: null means
  // this row's citations were never resolved at all, and it scores as pending.
  unconfirmed_citations?: UnconfirmedCitation[] | null;
  // #102, computed server-side: this row's status makes a claim its evidence
  // does not back, so the score withholds it. Derived rather than stored --
  // the status survives underneath so clearing a flag can put the technique
  // back into whichever of covered/partial/gap it says.
  pending_review?: boolean;
}

export interface UnconfirmedCitation {
  /** The capability this was applied as, or null when it resolved to nothing. */
  tool: string | null;
  /** What the model actually wrote. Null when it cited nothing at all. */
  cited: string | null;
  reason: string;
  /** Which of detection_tools / prevention_tools / response_tools it supported. */
  field: string | null;
  /**
   * null until a human vouches for the inference.
   *
   * Compare with `(x ?? null) === null`, not `x === null`. Every backend
   * reader uses `entry.get("cleared_at") is None`, so a MISSING key means
   * uncleared; a bare `=== null` here would read the same entry as cleared
   * and hide an outstanding review item. Not reachable through the API
   * today (pydantic always emits the key), which is why it is written down.
   */
  cleared_at: string | null;
}

export interface AttackAssessment {
  id: string;
  service_id: string;
  version: number;
  status: AttackAssessmentStatus;
  approved_at: string | null;
  approved_by: string | null;
  documents_stale?: boolean;
  coverage: AttackCoverageRow[];
}

export interface AttackCoveragePatch {
  status?: CoverageStatus | null;
  notes?: string;
  evidence_artifact_id?: string | null;
  locked?: boolean;
  detection_tools?: string[] | null;
  prevention_tools?: string[] | null;
  response_tools?: string[] | null;
  rationale?: string | null;
}

export interface CoverageChange {
  technique_code: string;
  field: string;
  old: unknown;
  new: unknown;
}

export interface AttackRunAiResponse {
  tools_available: number;
  changed: CoverageChange[];
  coverage: AttackCoverageRow[];
  // mitre_map runs as concurrent batches. Returned by the API since D-048 and
  // still rendered nowhere — a known gap recorded there, not this change's
  // business, but declared so the next reader sees it exists.
  batches_total?: number;
  batches_failed?: number;
  // W2 citation accounting. Optional so a stored payload from before the
  // resolver parses unchanged (C0).
  //
  // Every usable cited string lands in exactly one of the three:
  //   confirmed    — matched with no inference (case/whitespace only)
  //   needs_review — APPLIED, but the resolver had to change or assume
  //                  something. Inference is not confirmation.
  //   rejected     — no unique candidate; the citation is gone.
  citations_confirmed?: number;
  citations_needs_review?: number;
  citations_rejected?: number;
  citations_rejected_examples?: string[];
  citations_needs_review_tools?: string[];
  // Keyed by WHY — `incomplete_vendor_data` is a materially different risk from
  // `punctuation`, and collapsing them is what made that guard inert.
  citations_needs_review_by_reason?: Record<string, string[]>;
  // Entries that were not usable tool names at all. Not folded into `rejected`.
  citations_unusable?: number;
  // #102. TECHNIQUES this run left unbacked, not citations: one flagged tool
  // cited by forty techniques is one citation and forty pieces of review work.
  pending_review_rows?: number;
}

export interface TacticHeatmapEntry {
  tactic_id: string;
  tactic_name: string;
  technique_count: number;
  sub_technique_count: number;
  covered: number;
  partial: number;
  gap: number;
  not_applicable: number;
  unscored: number;
  pending_review?: number;
  coverage_pct: number;
}

export interface AttackHeatmap {
  assessment_id: string;
  version: number;
  total_techniques: number;
  total_sub_techniques: number;
  scored_count: number;
  unscored_count: number;
  covered: number;
  partial: number;
  gap: number;
  not_applicable: number;
  // #102. Techniques whose status is withheld from `coverage_pct` until their
  // evidence is confirmed. `coverage_pct` is a ratio over what can currently be
  // CLAIMED, so withholding narrows its denominator -- this count must be
  // rendered beside it, never dropped.
  pending_review?: number;
  coverage_pct: number;
  by_tactic: TacticHeatmapEntry[];
}

export interface AttackDeliverable {
  id: string;
  service_id: string;
  title: string;
  summary: string | null;
  version: number;
  pdf_artifact_id: string | null;
  xlsx_artifact_id: string | null;
  pdf_filename: string | null;
  xlsx_filename: string | null;
  finalized_at: string | null;
  finalized_by: string | null;
  /**
   * Issue 4: the API serializes this as `released_at` (see
   * app/schemas/*.py). The old name `released_to_client_at` never matched
   * any response field, so it was always undefined — harmless only
   * because nothing read it until the Release control was wired up.
   */
  released_at: string | null;
  superseded_by: string | null;
}

// ---------------------------------------------------------------------------
// Item 7 part 2 — GET /attack/services/{id}/ai-inputs.
//
// Mirrors `AttackAiInputsResponse` and friends in apps/api/app/schemas/attack.py
// field for field, derived by reading that file rather than from what the panel
// wanted to render.
//
// Every field is REQUIRED here even though its pydantic counterpart carries a
// default. The defaults are the C0 pattern on the SERVER — an older client
// parsing a newer response — and this endpoint has exactly one version, shipped
// with this panel. Marking them optional would license `?? 0` in the renderer,
// and a `?? 0` over `excluded_attribution` is precisely the silent under-report
// the endpoint exists to end.
// ---------------------------------------------------------------------------

/** The client-uploaded file a capability was extracted from. */
export interface AttackAiInputDocument {
  id: string;
  /** The sanitised original filename. */
  title: string;
  uploaded_at: string;
}

/**
 * Why a named capability on a list is not offered to the model.
 *
 * `not_in_approved_snapshot` names the observable STATE and not a cause: the
 * row was either created after approval or reclassified into scope after, and
 * nothing readable at request time separates those. Do not render it as either.
 */
export type AttackWithheldReason =
  "security_scope" | "not_in_approved_snapshot";

/**
 * How much the API may honestly say about rows dropped at extraction.
 *
 * A TRI-STATE, and the third member is the whole point. `unknown` must never
 * render as a number — `Reconciliation.attribution_complete` is not persisted,
 * so "nothing was excluded" and "attribution failed" are the same stored bytes
 * and the API refuses to collapse them into a zero. See `_excluded_attribution`
 * in apps/api/app/routes/attack.py.
 */
export type AttackExcludedAttribution = "not_recorded" | "complete" | "unknown";

/** One capability the model WILL be offered, and where it came from. */
export interface AttackAiInputCapability {
  name: string;
  vendor: string | null;
  category: string | null;
  security_functions: string[];
  /**
   * The model called this row non-security and no consultant has agreed yet.
   * Still in scope deliberately, and surfaced so a misclassification can be
   * caught before it becomes a fabricated gap.
   */
  awaiting_signoff: boolean;
  capability_list_id: string | null;
  source_list_version: number | null;
  source_document: AttackAiInputDocument | null;
  /**
   * A snapshot entry whose live row is gone (#96). It is still sent, under the
   * snapshot's own name, but it carries no description — so `category`,
   * `security_functions`, `awaiting_signoff` and `source_document` are all
   * absent-because-unreadable rather than empty. Renderers MUST say which:
   * "uncategorised" and "we cannot look" are different facts.
   */
  live_row_missing: boolean;
}

/** A named capability on a list that is NOT offered to the model. */
export interface AttackAiInputWithheld {
  name: string;
  vendor: string | null;
  reason: AttackWithheldReason;
  capability_list_id: string | null;
  source_list_version: number | null;
  source_document: AttackAiInputDocument | null;
}

/**
 * An uploaded SOURCE ROW that produced no capability at all.
 *
 * Not merged with `AttackAiInputWithheld`: this row never became a capability,
 * so it has no name to withhold. It is the earliest drop in the chain.
 */
export interface AttackAiInputExcludedRow {
  capability_list_id: string;
  index: number;
  summary: string;
}

/** A Tech Debt capability list contributing to — or held back from — the map. */
export interface AttackAiInputSourceList {
  capability_list_id: string;
  tech_debt_service_id: string;
  tech_debt_service_title: string;
  version: number;
  status: string;
  /**
   * False => a LATER version of the same list exists and this one still counts.
   * Every non-discarded version feeds the mapping, not just the newest.
   */
  is_latest_for_service: boolean;
  /** True when the APPROVED snapshot decides membership; false when live rows do. */
  membership_from_snapshot: boolean;
  /** The snapshot no longer matches current security scope; re-approval clears it. */
  membership_stale: boolean;
  sent_count: number;
  not_sent_count: number;
  /** Rows in the uploaded file. Null on a pre-0036 list, which makes no claim. */
  source_rows_total: number | null;
  excluded_attribution: AttackExcludedAttribution;
  /**
   * How many rows are NAMED in `excluded`, which is always literally true.
   * Deliberately not a count of what was excluded: under `unknown` this is zero
   * and the number excluded is not zero-or-anything-else known.
   */
  excluded_rows_named: number;
}

export interface AttackAiInputTotals {
  sent: number;
  not_sent: number;
  awaiting_signoff: number;
  withheld_security_scope: number;
  withheld_not_in_approved_snapshot: number;
  excluded_rows_named: number;
  /**
   * Contributing lists whose extraction-time exclusions cannot be reported.
   * Rendered beside `excluded_rows_named` for the same reason a withheld count
   * is rendered beside a coverage percentage: a total over an unknowable
   * population is not self-describing.
   */
  lists_with_unknown_exclusions: number;
  sent_without_source_document: number;
}

export interface AttackAiInputs {
  service_id: string;
  capabilities: AttackAiInputCapability[];
  not_sent: AttackAiInputWithheld[];
  excluded: AttackAiInputExcludedRow[];
  sources: AttackAiInputSourceList[];
  totals: AttackAiInputTotals;
}
