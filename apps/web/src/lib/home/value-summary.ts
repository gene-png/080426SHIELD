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
  attack_uncovered_count: number | null;
  attack_uncovered_unresolved: boolean;
  csf_gap_count: number | null;
  csf_gap_unresolved: boolean;
  csf_services: number;
  csf_targets_defaulted: number | null;
  csf_targets_unusable: number | null;
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
  const scope =
    assumed === p.services
      ? `Counted against the standard ${p.unit}`
      : `${assumed} of ${p.services} ${p.noun} counted against the standard ${p.unit}`;
  return `${scope} — ${why}.`;
}

/**
 * The hint under a gap figure, with "your" removed when it would be false.
 *
 * One rule rather than three: the possessive survives only when every summand
 * used the client's own choice. A mixed set is not "your target" for the part
 * that was assumed, and `assumedTargetNote` says how much of it.
 */
export function gapHint(p: TargetProvenance, subject: string): string {
  const possessive = targetIsWhollyTheClients(p) ? "your " : "the ";
  return `${subject} below ${possessive}target maturity ${p.unit}.`;
}
