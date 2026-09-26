/**
 * #554: the two counts outside the assessed denominator, as every surface
 * states them BESIDE the percentage -- the same words the deliverable uses
 * (`outside_assessed_text` in the API's `attack/exporters.py`).
 *
 * Never dropped, even at zero, unlike "pending review" (which the admin card
 * hides at zero on purpose): the owner's rule is that no surface showing the
 * percentage may drop the not-verified count, so "none" and "not shown" must
 * never look alike.
 */
export function outsideAssessedText(r: {
  unable_to_determine?: number | null;
  outside_control_surface?: number | null;
}): string | null {
  // Option (a), 2026-09-26: the API sends the counts only for an assessment
  // under #620's rules (`attack/rules.py`). One approved before #620 renders
  // what was delivered, so absent counts mean "not stated here" -- null, never
  // a confident "Not verified 0".
  if (r.unable_to_determine == null || r.outside_control_surface == null) {
    return null;
  }
  return `Not verified ${r.unable_to_determine}, Outside control surface ${r.outside_control_surface}.`;
}
