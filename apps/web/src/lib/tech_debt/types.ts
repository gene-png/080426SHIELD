import type { AiSource } from "@/lib/aiSource/types";

export type SecurityFunction = "prevent" | "detect" | "respond";

/** Wire types mirroring apps/api/app/schemas/tech_debt.py. */

export type ServiceKind =
  | "tech_debt"
  | "zero_trust_cisa"
  | "zero_trust_dod"
  | "nist_csf"
  | "attack_coverage";

export type ServiceStatus =
  "draft" | "in_progress" | "review" | "released" | "archived";

export type CapabilityListStatus =
  "draft" | "approved" | "released" | "discarded";

export type CapabilityDisposition = "keep" | "consolidate" | "cut";

export interface ServiceResponse {
  id: string;
  kind: ServiceKind;
  status: ServiceStatus;
  title: string;
  source_request_id: string | null;
  opened_by: string;
  released_at: string | null;
  created_at: string;
}

export interface CapabilityItem {
  /** Set when this row is a component named inside a bundled licence. */
  parent_item_id?: string | null;
  id: string;
  capability_list_id: string;
  name: string;
  vendor: string | null;
  category: string | null;
  function: string | null;
  annual_cost_usd: number | null;
  license_count: number | null;
  notes: string | null;
  confidence_pct: number | null;
  /**
   * Security classification (migration 0038). Tri-state: null means nobody has
   * classified this row, which is NOT the same as "not security-related" — an
   * unclassified row stays in the ATT&CK subset.
   */
  security_related?: boolean | null;
  security_functions?: SecurityFunction[];
  /** A consultant has agreed with a NEGATIVE classification. */
  security_class_confirmed?: boolean;
  /**
   * #845: how the sign-off queue words this row. "not_in_use" is a security
   * tool the extraction marked "Security tool not in use:" (v3.2); null when
   * the row is not awaiting sign-off.
   */
  signoff_kind?: "not_in_use" | "not_security" | null;
  source_artifact_id: string | null;
  disposition: CapabilityDisposition | null;
  disposition_rationale: string | null;
  consolidation_target_id: string | null;
}

export interface ExcludedRow {
  index: number;
  summary: string;
  /** A consultant reviewed this exclusion and agrees with it. */
  confirmed?: boolean;
}

/** C6 (for #806): one count per rule, from the api's `extraction_flags`. */
export interface ExtractionFlagCounts {
  name_missing: number;
  confidence_off_scale: number;
  category_off_list: number;
  source_row_duplicated: number;
}

/** #833 / #834: one value the extraction could not store as given. */
export interface ExtractionFinding {
  source_row_index: number | null;
  item_name: string;
  field: string;
  reason: string;
  value: string;
  /** The column width a string was shortened to (reason "truncated"). */
  width?: number;
}

export interface CapabilityList {
  /** #177: whether the extraction attributed every item to one uploaded row;
   *  null is "not recorded". */
  attribution_complete?: boolean | null;
  /** #833 / #834: null is "not recorded" (a list from before the check);
   *  [] is "checked, nothing to record". */
  extraction_findings?: ExtractionFinding[] | null;
  /** #177/#193: from the api's one reader. "exact" licenses the excluded count
   *  as the count; "unknown" makes it a floor. Absent reads as unknown. */
  exclusion_count_state?: "not_recorded" | "exact" | "unknown" | null;
  /** #845: rows marked "Security tool not in use:" that were also given
   *  security functions, so they stay in the ATT&CK assessment. */
  not_in_use_contradictions?: number;
  /** C6 (for #806): what Tech Debt prompt v3.2 closes and the AI still sent,
   *  each value kept as sent. Null is "not measured": a list an earlier prompt
   *  drafted, or one no extraction is on record for. */
  extraction_flags?: ExtractionFlagCounts | null;
  /** #646: which mode drafted this list, as the API states it. Null only on
   *  a response built without it. */
  ai_source?: AiSource | null;
  id: string;
  service_id: string;
  version: number;
  status: CapabilityListStatus;
  items: CapabilityItem[];
  approved_at: string | null;
  /**
   * #640: the approval covers the list as it stands. False for a draft, and
   * false again after any step-2 edit to an approved list until step 3
   * approves it again; finalize and release refuse while it is false.
   */
  approval_current: boolean;
  approved_by: string | null;
  /** Rows in the source upload. Null on lists extracted before 0036. */
  source_rows_total?: number | null;
  /** Uploaded rows that produced no capability. Empty when unattributable. */
  excluded_rows?: ExcludedRow[];
}

export interface CapabilityItemPatch {
  name?: string;
  vendor?: string;
  category?: string;
  function?: string;
  annual_cost_usd?: number | null;
  license_count?: number | null;
  notes?: string;
  disposition?: CapabilityDisposition | null;
  disposition_rationale?: string;
  consolidation_target_id?: string | null;
}

export interface ConsolidationPlanSummary {
  capability_list_id: string;
  capability_list_version: number;
  total_items: number;
  keep_count: number;
  consolidate_count: number;
  cut_count: number;
  undecided_count: number;
  estimated_annual_savings: number;
  savings_cost_known: boolean;
}

/** #804: what proposed dispositions would make the savings figure. Computed
 *  by the API with the deliverable's own derivation; nothing is written. */
export interface SavingsPreview {
  capability_list_id: string;
  estimated_annual_savings: number;
  savings_cost_known: boolean;
  keep_count: number;
  consolidate_count: number;
  cut_count: number;
  undecided_count: number;
}

export interface OverlapBucket {
  key: string;
  item_count: number;
  total_cost: number;
  cost_known: boolean;
  item_ids: string[];
  item_names: string[];
}

export interface TopCostItem {
  id: string;
  name: string;
  vendor: string | null;
  category: string | null;
  annual_cost_usd: number;
}

export interface OverlapAnalysis {
  capability_list_id: string;
  capability_list_version: number;
  by_category: OverlapBucket[];
  by_vendor: OverlapBucket[];
  top_cost_items: TopCostItem[];
  total_cost: number;
  /** #781: what `total_cost` may honestly be called -- the deliverable's own
   *  `cost_label` for this list: "Total annual cost", "Included annual cost"
   *  or "Annual cost (may not be complete)". */
  total_cost_label: string;
  total_items: number;
  uncategorized_count: number;
  no_vendor_count: number;
  no_cost_count: number;
}

export interface Deliverable {
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
