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
  unable_to_determine: number;
  outside_control_surface: number;
}): string {
  return `Not verified ${r.unable_to_determine}, Outside control surface ${r.outside_control_surface}.`;
}
