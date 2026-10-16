/**
 * CSF self-rating copy, APPROVED by Gene (#736 6205956728) as written in the
 * text package (6204461502) under the number beside each string. Plain
 * strings and the formatting they need. Tests type their own copies rather
 * than importing these.
 */

/** The client's self-rating tiers by name, as the questionnaire and the
 * csf_score prompt name them. */
export const RATING_NAMES: Readonly<Record<number, string>> = {
  1: "Partial",
  2: "Risk Informed",
  3: "Repeatable",
  4: "Adaptive",
};

/** A rating tier's name. A value outside 1..4 is a defect upstream, so it
 * throws rather than render a made-up name. */
export function ratingName(tier: number): string {
  const name = RATING_NAMES[tier];
  if (name === undefined) {
    throw new Error(`CSF rating tier ${String(tier)} has no name`);
  }
  return name;
}

/** W5: a self-rating gap, current to target, by name. */
export function ratingGap(current: number, target: number): string {
  return `${ratingName(current)} → ${ratingName(target)}`;
}

/**
 * W6: the gap list's priority with its working, e.g. "Priority 1.1: 1 tier
 * below target × 1.15 (Protect weighting)". The priority has one decimal,
 * ROUNDED DOWN, and the weight is shown as stored. Computed in integer
 * hundredths of the weight, so the floor is exact by construction: a float
 * product can sit just below a tenth (3 × 1.2 is 3.5999…). Measured: over
 * today's weights and gaps of 1 to 3, flooring `gap × weight × 10` happens to
 * agree, so this guards a weight change rather than a case reachable now.
 * `app/deliverable_priority.py::floored_priority` (API) computes it the same way.
 */
export function priorityWorking(
  gapSize: number,
  weight: number,
  functionName: string,
): string {
  if (!Number.isFinite(weight) || !Number.isInteger(gapSize)) {
    // An API without `weight` (or a broken one) would otherwise print "NaN".
    throw new Error(
      `CSF gap priority needs a weight and a whole gap; got ${String(weight)}, ${String(gapSize)}`,
    );
  }
  const tenths = Math.floor((gapSize * Math.round(weight * 100)) / 10);
  const p = `${Math.floor(tenths / 10)}.${tenths % 10}`;
  const tiers = gapSize === 1 ? "tier" : "tiers";
  // As stored: the API's 1.0 arrives as the number 1, so a whole weight keeps
  // its one decimal ("× 1.0", not "× 1").
  const w = Number.isInteger(weight) ? weight.toFixed(1) : String(weight);
  return `Priority ${p}: ${gapSize} ${tiers} below target × ${w} (${functionName} weighting)`;
}

/** C9: the client dashboard's "Current maturity" sub-line. */
export const CURRENT_MATURITY_SUB =
  "Averaged across all functions. Self-reported, not validated.";
