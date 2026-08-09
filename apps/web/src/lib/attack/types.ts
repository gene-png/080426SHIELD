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
  /**
   * Citations the model made that code could not match to an approved
   * capability, and ones it resolved from a near miss. These MUST be shown: an
   * unresolved citation is a technique that will read as uncovered for a reason
   * that is not the client's security posture, and a count nobody sees is the
   * same silent failure the resolver was written to end.
   */
  citations_normalized: number;
  citations_rejected: number;
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

/**
 * What the mapping will run against, from
 * `GET /attack/services/{id}/ai-inputs`.
 *
 * The workspace previously showed only a count, and only after the run. Every
 * array is optional-by-default on the API side so an older client parses a
 * newer response.
 */
export interface AttackAiInputDocument {
  id: string;
  title: string;
  mime_type: string;
  size_bytes: number;
  uploaded_at: string;
  item_count: number;
}

export interface AttackAiInputList {
  capability_list_id: string;
  tech_debt_service_id: string;
  tech_debt_service_title: string;
  version: number;
  status: string;
  /** False => a newer version exists and this one STILL feeds the mapping. */
  is_latest_for_service: boolean;
  item_count: number;
}

export interface AttackAiInputItem {
  name: string;
  vendor: string | null;
  category: string | null;
  security_functions: string[];
  /** The model called it non-security; nobody has agreed yet. Still in scope. */
  awaiting_signoff: boolean;
  source_document_id: string | null;
  capability_list_id: string;
  list_label: string;
  list_is_superseded: boolean;
}

export interface AttackAiInputs {
  service_id: string;
  /** Equals the run's `tools_available`, by construction. */
  tools_sent: number;
  items_in_scope: number;
  duplicate_names: number;
  awaiting_signoff_count: number;
  items_without_source_document: number;
  /** On an unapproved draft list, held back until someone vouches for them. */
  draft_excluded_count: number;
  draft_lists_count: number;
  documents: AttackAiInputDocument[];
  lists: AttackAiInputList[];
  items: AttackAiInputItem[];
}
