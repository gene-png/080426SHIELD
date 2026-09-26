/**
 * What the value card may truthfully call the target its figures were counted
 * against (#207).
 *
 * The ZT and CSF slots on that card are SUMS across every released service of
 * their kind, and each summand is counted against a target resolved from the
 * client's stored choice -- where that choice was usable. Where it was absent,
 * out of range, or unparseable, the engine default applied. The API computed
 * that attribution and dropped it, so the card said "your target maturity
 * stage" over a stage the client may never have seen.
 *
 * The repair is not a source LABEL. There is no honest single source for a
 * mixed set -- one engagement on the client's own stage and another on the
 * default is neither "client" nor "default" -- so the API publishes COUNTS and
 * this module turns them into a sentence.
 *
 * ## What is kept apart, and what is deliberately not
 *
 * "Chose nothing" and "chose something unusable" stay separate, the whole way,
 * for the reason `lib/dashboards/zt.ts::targetFault` states: collapsing them
 * tells a client they made no choice when they made one that was discarded --
 * a lie in their own words, and only the second is answerable by re-asking
 * them.
 *
 * `client_out_of_range` and `client_unparseable` ARE collapsed here, into "the
 * one on file could not be used". That is a coarser split than the per-service
 * dashboards make, and it is deliberate: this card sums across services, so a
 * sentence naming one precise fault would be false the moment two services fail
 * differently. The dashboard one click away carries the precise fault per
 * service. Stated so it reads as a decision rather than as an oversight.
 */

export interface ValueSummary {
  tech_debt_savings_usd: number | null;
  tech_debt_savings_cost_known: boolean;
  tech_debt_savings_unresolved: boolean;
  zt_gap_count: number | null;
  zt_gap_unresolved: boolean;
  zt_services: number;
  zt_targets_defaulted: number | null;
  zt_targets_unusable: number | null;
  /** #209: summands counted against a LIVE target rather than the one
   *  their released report was rendered against. See `liveTargetNote`. */
  zt_targets_computed_live: number | null;
  attack_uncovered_count: number | null;
  attack_uncovered_unresolved: boolean;
  /** #556: unresolved BECAUSE the released ATT&CK report is withheld (another
   *  catalog), not because the figure cannot be matched (#114). */
  attack_uncovered_withheld: boolean;
  csf_gap_count: number | null;
  csf_gap_unresolved: boolean;
  csf_services: number;
  csf_targets_defaulted: number | null;
  csf_targets_unusable: number | null;
  /** The CSF twin of `zt_targets_computed_live`. */
  csf_targets_computed_live: number | null;
  has_any_data: boolean;
  has_unresolved: boolean;
}

export interface TargetProvenance {
  /** Released services of this kind the figure sums over. The denominator. */
  services: number;
  /** Summands where the client chose nothing and the engine default applied. */
  defaulted: number | null;
  /** Summands where the client's stored choice could not be used. */
  unusable: number | null;
  /** #209: summands whose target was read LIVE rather than frozen at the
   *  moment their report was rendered. A THIRD fact, not a flavour of the
   *  two above: a live-read target may well be the client's own current
   *  choice, so both of those stay 0 while the figure still need not match
   *  the delivered document. */
  computedLive: number | null;
  /** "stage" for ZT, "tier" for CSF — the client's word for the target. */
  unit: string;
  /** What the figure is summed over, plural, in the client's words. */
  noun: string;
}

/**
 * How many summands were counted against a target the client did not choose,
 * or `null` when that is not a measured fact.
 *
 * `null` propagates rather than becoming `0`. The API sends null for both
 * counts whenever the figure itself is null -- a kind goes unresolved wholesale
 * and returns on the first unresolvable service, so any tally reached by then
 * describes a prefix of a sum nobody published. A `0` here would render as
 * "nothing was assumed" over something nobody measured, which is the reassuring
 * direction the standing rule forbids.
 */
export function assumedTargetCount(p: TargetProvenance): number | null {
  if (p.defaulted === null || p.unusable === null) return null;
  return p.defaulted + p.unusable;
}

/** True when the card may still say "YOUR target" about this figure. */
export function targetIsWhollyTheClients(p: TargetProvenance): boolean {
  return assumedTargetCount(p) === 0;
}

/**
 * The sentence disclosing assumed targets, or `null` when there is nothing to
 * disclose.
 *
 * Never an imperative. A user-facing string naming an action has to name a
 * control that exists and works today, and a client cannot change their
 * engagement target from this card -- so this states the fact and stops. The
 * per-service dashboard is where the same fact appears beside the thing that
 * can act on it.
 */
export function assumedTargetNote(p: TargetProvenance): string | null {
  const assumed = assumedTargetCount(p);
  if (assumed === null || assumed === 0) return null;

  const faults: string[] = [];
  // Order is fixed rather than data-dependent, so two clients with the same
  // two faults read the same sentence.
  if (p.defaulted && p.defaulted > 0)
    faults.push(`no ${p.unit} chosen at intake`);
  if (p.unusable && p.unusable > 0)
    faults.push(`the ${p.unit} on file could not be used`);

  const why = faults.join("; ");
  // "the DEFAULT stage", matching `lib/dashboards/zt.ts::targetNote` and
  // `CsfDashboard.tsx`, which both say "Default target" for this same fact.
  //
  // The first draft said "the standard stage", and that is a loaded word in
  // this product's own domain: CISA ZTMM 2.0 DEFINES Stage 1-4, so "the
  // standard stage" reads as "the framework's benchmark" -- reassurance that an
  // authoritative target was applied, which inverts a sentence whose whole job
  // is to disclose that we assumed one. A client clicking through to the ZT
  // dashboard for the same engagement would then read "Default target" for what
  // the card called standard: two words, one fact, and only one of them says
  // "we picked this".
  const scope =
    assumed === p.services
      ? `Counted against the default ${p.unit}`
      : `${assumed} of ${p.services} ${p.noun} counted against the default ${p.unit}`;
  return `${scope} — ${why}.`;
}

/**
 * The hint under a gap figure, with "your" removed when it would be false.
 *
 * One rule rather than three: the possessive survives only when every summand
 * used the client's own choice. A mixed set is not "your target" for the part
 * that was assumed, and `assumedTargetNote` says how much of it.
 */
/**
 * The sentence disclosing figures counted against a LIVE target, or `null`.
 *
 * SEPARATE FROM `assumedTargetNote`, deliberately. That one returns null when
 * nothing was assumed, and a live-read target is not an assumed one -- a client
 * who chose their own stage at intake has `defaulted === 0` and
 * `unusable === 0`, so folding this into it would drop the disclosure in
 * exactly the commonest case. `CLAUDE.md` records that shape: a conditional
 * added so a value is not charged twice becomes the path that records nothing.
 *
 * `null` propagates rather than becoming `0`, for the reason
 * `assumedTargetCount` gives: the API sends null whenever the figure itself is
 * null, and a `0` would read as "every figure matches your reports" over
 * something nobody measured.
 *
 * Never an imperative: a client cannot re-render a report from this card.
 */
export function liveTargetNote(p: TargetProvenance): string | null {
  if (p.computedLive === null || p.computedLive === 0) return null;
  const scope =
    p.computedLive === p.services
      ? `Counted against your target as it stands today`
      : `${p.computedLive} of ${p.services} ${p.noun} counted against your target as it stands today`;
  return `${scope} — your released report was rendered against the ${p.unit} on file at the time, so the two can differ.`;
}

/**
 * Both target disclosures for one kind, joined, or `null` when neither fires.
 *
 * ONE composer so the card cannot render one disclosure and forget the other.
 * The card has a single note slot, and the alternative -- calling both helpers
 * at each of the two call sites -- is four places for two facts, which is how
 * one service ends up disclosing something the other does not.
 */
export function targetNotes(p: TargetProvenance): string | null {
  const notes = [assumedTargetNote(p), liveTargetNote(p)].filter(
    (n): n is string => n !== null,
  );
  return notes.length === 0 ? null : notes.join(" ");
}

export function gapHint(p: TargetProvenance, subject: string): string {
  const possessive = targetIsWhollyTheClients(p) ? "your " : "the ";
  return `${subject} below ${possessive}target maturity ${p.unit}.`;
}
