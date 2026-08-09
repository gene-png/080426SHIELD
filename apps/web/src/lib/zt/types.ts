/** Wire types mirroring apps/api/app/schemas/zt.py. */

export type ZtFramework = "cisa_ztmm_2_0" | "dod_ztra";
export type ZtAssessmentStatus =
  "draft" | "submitted" | "approved" | "released" | "discarded";

export interface CatalogCapability {
  code: string;
  pillar_code: string;
  name: string;
  outcome: string;
}

export interface CatalogPillar {
  code: string;
  name: string;
  purpose: string;
  capabilities: CatalogCapability[];
}

export interface CatalogStage {
  stage: number;
  label: string;
  description: string;
}

export interface ZtCatalog {
  framework: ZtFramework;
  pillars: CatalogPillar[];
  stages: CatalogStage[];
  total_capabilities: number;
}

export interface ZtAnswer {
  id: string;
  assessment_id: string;
  capability_code: string;
  maturity_stage: number | null;
  target_stage?: number | null;
  locked?: boolean;
  notes: string | null;
  evidence_artifact_id: string | null;
  answered_by: string | null;
  answered_at: string | null;
}

export interface ZtAssessment {
  id: string;
  service_id: string;
  framework: ZtFramework;
  version: number;
  status: ZtAssessmentStatus;
  approved_at: string | null;
  approved_by: string | null;
  documents_stale?: boolean;
  answers: ZtAnswer[];
  client_target_stage: number | null;
}

export interface ZtAnswerPatch {
  maturity_stage?: number | null;
  target_stage?: number | null;
  locked?: boolean;
  notes?: string;
  evidence_artifact_id?: string | null;
}

export interface ZtCapabilityChange {
  capability_code: string;
  field: string;
  old: unknown;
  new: unknown;
}

export interface ZtRunAiResponse {
  changed: ZtCapabilityChange[];
  answers: ZtAnswer[];
  pillar_narratives: Record<string, string>;
  executive_summary: string | null;
  roadmap_summary: string | null;
  /**
   * Answers the AI did not write that an offline run left alone — submitted,
   * in progress, or consultant-entered. 0 for a live run.
   */
  preserved_client_answers?: number;
  /**
   * Individual stage values the model returned outside the framework range, so
   * they were not applied. Counted per value. Narrow by design: 0 means "no
   * value was out of range", NOT "nothing was dropped".
   */
  rejected_stage_values?: number;
  /**
   * Entries that could not be read as a capability at all (non-object entry,
   * unusable code, or a non-list `capabilities`). Separate from
   * `rejected_stage_values`: there is nothing to apply them to.
   */
  unusable_suggestions?: number;
}

export interface PillarScore {
  pillar_code: string;
  pillar_name: string;
  capability_count: number;
  answered_count: number;
  average_stage: number | null;
  coverage_pct: number;
  weakest_capability_codes: string[];
}

export interface ZtScoreSummary {
  assessment_id: string;
  version: number;
  framework: ZtFramework;
  total_capabilities: number;
  answered_capabilities: number;
  coverage_pct: number;
  average_stage: number | null;
  overall_stage_label: string;
  by_pillar: PillarScore[];
}

export interface GapItem {
  code: string;
  pillar_code: string;
  pillar_name: string;
  name: string;
  outcome: string;
  current_stage: number;
  target_stage: number;
  gap_size: number;
  priority_score: number;
  notes: string | null;
}

export interface GapAnalysis {
  assessment_id: string;
  version: number;
  framework: ZtFramework;
  target_stage: number;
  target_label: string;
  total_gap_count: number;
  unscored_count: number;
  gap_count_by_pillar: Record<string, number>;
  gaps: GapItem[];
  roadmap?: RoadmapEntry[];
}

export interface RoadmapEntry {
  month: number;
  code: string;
  pillar_code: string;
  pillar_name: string;
  name: string;
  current_stage: number;
  target_stage: number;
  priority_score: number;
}

export interface ZtDeliverable {
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
