import type { AiSource } from "@/lib/aiSource/types";

/** Wire types mirroring apps/api/app/schemas/csf.py. */

export type CsfAssessmentStatus =
  "draft" | "submitted" | "approved" | "released" | "discarded";

export interface CatalogSubcategory {
  code: string;
  function: string;
  category: string;
  name: string;
  outcome: string;
  /** Minimum impact profile (LOW/MOD/HIGH) at which this outcome applies. */
  min_profile: string;
}

export interface CatalogCategory {
  code: string;
  function: string;
  name: string;
  purpose: string;
  subcategories: CatalogSubcategory[];
}

export interface CatalogFunction {
  code: string;
  name: string;
  purpose: string;
  categories: CatalogCategory[];
}

export interface CatalogTier {
  tier: number;
  short_label: string;
  description: string;
}

export interface CsfCatalog {
  functions: CatalogFunction[];
  tiers: CatalogTier[];
  total_subcategories: number;
}

export interface CsfAnswer {
  id: string;
  assessment_id: string;
  subcategory_code: string;
  maturity_tier: number | null;
  notes: string | null;
  evidence_artifact_id: string | null;
  answered_by: string | null;
  answered_at: string | null;
}

export interface CsfAssessment {
  /** #646: which mode drafted the AI suggestions, as the API states it. */
  ai_source: AiSource;
  id: string;
  service_id: string;
  version: number;
  status: CsfAssessmentStatus;
  approved_at: string | null;
  approved_by: string | null;
  documents_stale?: boolean;
  answers: CsfAnswer[];
  client_target_tier: number | null;
  client_profile: string | null;
  /**
   * #852: answers kept on a subcategory the catalog no longer has (ID.AM-09),
   * not scored, with the API's approved sentence (`csf/retired.py`). Render
   * the sentence as given; never rebuild it here.
   */
  retired_answers?: number;
  retired_answers_note?: string | null;
}

/**
 * Body for `PATCH /csf/answers/{id}` (admin).
 *
 * The API also has a narrower `CsfSelfAssessmentAnswerPatch` for the CLIENT
 * route, which now refuses `evidence_artifact_id` and `locked` with a typed
 * 422 instead of dropping them behind a 200 (#195's CSF twin).
 *
 * NO matching narrow type is declared here, deliberately, and the reason is
 * structural rather than an oversight: `CsfSelfAssessment` renders the ADMIN
 * `CsfQuestionnaire` component, whose `onAnswerUpdate` prop is typed to this
 * interface. Narrowing the client path's type would not compile until that
 * shared component is split -- a refactor with real regression surface, and
 * wider than the defect. The ZT side has its own JSX and no shared component,
 * so `ZtSelfAssessmentAnswerPatch` exists there.
 *
 * Safe as it stands: `CsfQuestionnaire` only ever sends `maturity_tier` and
 * `notes`, both of which the client route applies. The API is the enforcing
 * layer either way.
 */
export interface CsfAnswerPatch {
  maturity_tier?: number | null;
  notes?: string;
  evidence_artifact_id?: string | null;
}

export interface CsfInterviewQuestion {
  external_id: string;
  section_name: string;
  order_index: number;
  stem: string;
  cues: string[];
  /** CSF 2.0 subcategory codes this prompt informs. */
  csf_subcategories: string[];
}

export interface CsfInterviewQuestionnaire {
  framework_key: string;
  profile: string | null;
  questions: CsfInterviewQuestion[];
}

export interface FunctionScore {
  function: string;
  function_name: string;
  subcategory_count: number;
  answered_count: number;
  average_tier: number | null;
  coverage_pct: number;
  weakest_subcategory_codes: string[];
}

export interface CsfScoreSummary {
  assessment_id: string;
  version: number;
  total_subcategories: number;
  answered_subcategories: number;
  coverage_pct: number;
  average_tier: number | null;
  overall_maturity_label: string;
  by_function: FunctionScore[];
}

export interface GapItem {
  code: string;
  function: string;
  function_name: string;
  category: string;
  name: string;
  outcome: string;
  current_tier: number;
  target_tier: number;
  gap_size: number;
  priority_score: number;
  notes: string | null;
}

export interface GapAnalysis {
  assessment_id: string;
  version: number;
  target_tier: number;
  target_label: string;
  total_gap_count: number;
  unscored_count: number;
  gap_count_by_function: Record<string, number>;
  gaps: GapItem[];
}

export interface CsfDeliverable {
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

// --- Full-Playbook tiered Working Profile (Work Order D4) ---

export interface CsfDimensionScore {
  id: string;
  tier: string;
  subcategory_code: string;
  governance: number;
  policy: number;
  implementation: number;
  monitoring: number;
  improvement: number;
  in_scope: boolean;
  rationale: string | null;
  what_we_found: string | null;
  has_evidence: boolean;
  target_level: number | null;
  locked: boolean;
  total: number;
  level: number;
  evidence_capped: boolean;
}

export interface CsfProfile {
  tier: string;
  rows: CsfDimensionScore[];
}

export interface CsfDimensionScorePatch {
  governance?: number;
  policy?: number;
  implementation?: number;
  monitoring?: number;
  improvement?: number;
  in_scope?: boolean;
  rationale?: string | null;
  what_we_found?: string | null;
  has_evidence?: boolean;
  target_level?: number | null;
  locked?: boolean;
}

export interface EnterpriseSubcategory {
  subcategory_code: string;
  name: string;
  function: string;
  tier_levels: Record<string, number>;
  enterprise_level: number;
  rollup_rule: number;
  target_level: number | null;
  gap: boolean;
  priority: string | null;
  /**
   * #1000: the subcategory's interview answer has no notes, so a LIVE run does
   * not assess its rows. From current notes, at read time. Read as
   * `=== true`: a response without it says nothing.
   */
  no_notes?: boolean;
}

export interface EnterpriseProfile {
  tiers_in_use: string[];
  subcategories: EnterpriseSubcategory[];
  /**
   * #852: Working Profile rows kept on a subcategory the catalog no longer
   * has, not rolled up, with the API's approved sentence (`csf/retired.py`).
   */
  retired_rows?: number;
  retired_rows_note?: string | null;
}

export interface CsfDimensionChange {
  tier: string;
  subcategory_code: string;
  field: string;
  old: unknown;
  new: unknown;
}

/**
 * One suggestion the AI run did not apply, and why (W1, issue #44).
 *
 * `locked` is a by-design skip — a human locked that row — and renders apart
 * from the rest. Folding it into a single "N dropped" number rebuilds the
 * alert-fatigue problem issue #31 rejected: a warning that fires during normal
 * work gets trained away, and takes the real ones with it.
 */
export interface CsfDroppedSuggestion {
  /**
   * Kept in step with the `Literal` on the API's `CsfDroppedSuggestion.reason`.
   * The union is not exhaustive at runtime — the payload arrives as JSON — so
   * the panel falls back to showing the raw code rather than an empty bullet.
   */
  reason:
    | "entry_shape"
    | "unknown_key"
    | "unknown_field"
    | "unparseable"
    | "out_of_range"
    | "wrong_type"
    | "superseded"
    | "locked"
    | "protected"
    | "edited"
    | "not_in_batch"
    | "no_notes";
  /** "tier|subcategory_code" as the model wrote it; null if it wrote neither. */
  key: string | null;
  field: string | null;
  /** How many suggested values this one record accounts for. */
  values: number;
  value: unknown;
}

/**
 * What a csf_score Run-AI did: the run's stored `result` since #645, every
 * field the synchronous response carried, read from the run so it survives a
 * reload.
 */
export interface CsfRunAiResponse {
  changed: CsfDimensionChange[];
  rows: CsfDimensionScore[];
  /** Counted in suggested VALUES (one field on one row), not entries. */
  suggestions_received: number;
  suggestions_applied: number;
  dropped: CsfDroppedSuggestion[];
  /**
   * #479: csf_score runs in batches. A failed batch's rows were never
   * answered, so they are in neither count above. Optional: a result stored
   * before batching carries neither, and that is not "no batch failed".
   */
  batches_total?: number;
  batches_failed?: number;
  /**
   * #836: rows a successful batch was asked for that no entry of that batch
   * named; they keep their previous scores. Optional: a result stored before
   * this carries neither. Read the VALUE, never the presence.
   */
  omitted_count?: number;
  omitted_rows?: { tier: string; subcategory_code: string }[];
  /**
   * #1000: rows a LIVE run did not assess because their answer had no notes.
   * null on an offline run and absent on a result stored before #1000: "not
   * counted", never zero. Read the VALUE: shown only when it is a number.
   */
  no_notes_count?: number | null;
  /** #1000: what the client Playbook files state, in subcategories. */
  no_notes_subcategories?: number | null;
  no_notes_subcategories_total?: number | null;
}

export interface ExportedArtifact {
  kind: string;
  label: string;
  artifact_id: string;
  filename: string;
}

export interface CsfPlaybookExport {
  artifacts: ExportedArtifact[];
}

// --- POA&M / gap action plan (Sprint 5 T5, spec step 10) ---

export type GapCharacterization = "accept" | "mitigate" | "transfer" | "avoid";

export interface CsfGapAction {
  subcategory_code: string;
  name: string;
  function: string;
  enterprise_level: number;
  target_level: number | null;
  /** Code-computed default from gap_priority() via the Enterprise roll-up. */
  default_priority: string | null;
  characterization: string | null;
  priority_override: string | null;
  owner: string | null;
  deadline: string | null;
  resources: string | null;
  success_criteria: string | null;
  poam_ref: string | null;
  /** priority_override where set, else default_priority. */
  effective_priority: string | null;
}

export interface CsfGapActions {
  assessment_id: string;
  actions: CsfGapAction[];
}

export interface CsfGapActionUpsert {
  characterization?: string | null;
  priority_override?: string | null;
  owner?: string | null;
  deadline?: string | null;
  resources?: string | null;
  success_criteria?: string | null;
  poam_ref?: string | null;
}
