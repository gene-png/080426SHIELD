import type { CapabilityDisposition } from "./types";

/**
 * #804: what each stored disposition is CALLED, everywhere a person reads it:
 * the admin table and its bulk bar, the help text, the plan card, the savings
 * what-if and the client dashboard. One map, so a rename lands everywhere at
 * once. The stored value `consolidate` keeps its name (no migration); only its
 * label changed, to "Cut, covered by another tool" (Gene, 2026-10-02 on #801).
 *
 * The API's twin is `tech_debt/exporters.py::_disposition_label`, which labels
 * the PDF, DOCX and XLSX. Reword one and you must reword the other.
 */
export const DISPOSITION_LABEL: Record<CapabilityDisposition, string> = {
  keep: "Keep",
  cut: "Cut",
  consolidate: "Cut, covered by another tool",
};
