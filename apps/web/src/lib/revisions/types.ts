/**
 * #1120: what a revision copied and why, as the API serves it on the ATT&CK,
 * CSF and ZT assessment responses (`revision`; NULL unless a revision minted
 * the record). Read by the V3, V4 and V5 banners.
 */
export interface RevisionInfo {
  from_version: number;
  started_by_name: string;
  started_at: string;
  reason: string;
  /** The source was approved under earlier rules (V3). */
  rules_changed: boolean;
  /** ATT&CK codes the current catalog no longer holds, not copied (V4). */
  retired_codes: string[];
}
