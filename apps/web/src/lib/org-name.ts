/**
 * How an organisation's name is rendered when it does not have one yet.
 *
 * `Client.legal_name` is nullable on the API since D-080 (#254): NULL means
 * nobody has named the organisation, which is the state every self-serve
 * signup starts in. Before that, self-serve provisioning derived a name from
 * the registrant's email -- the domain, or for a personal mailbox the PERSON'S
 * OWN NAME -- and that string reached client deliverables as the organisation.
 *
 * ## Why the string lives HERE and not at each call site
 *
 * "(pending intake)" used to be a value the API stored and thirteen server-side
 * conditionals compared against. It is now COPY: a label this layer prints when
 * `legal_name` is null, and nothing branches on it. The distinction is the
 * whole of D-080 -- one representation of "unnamed" (the null) and one
 * rendering of it (this label), rather than two representations that can
 * disagree.
 *
 * Keeping the literal in one module is what stops it drifting back into a
 * condition: a component that imports `orgDisplayName` cannot accidentally
 * reintroduce `legal_name === "(pending intake)"`, because it never sees the
 * string.
 */

/**
 * Shown wherever an unnamed organisation needs a label.
 *
 * Deliberately the same words the API used to store, so an admin who has seen
 * this phrase before reads it as the same state. It is not sent to the server
 * and is never written back.
 */
export const UNNAMED_ORG_LABEL = "(pending intake)";

/**
 * True when a human has named this organisation.
 *
 * Treats the empty string as unnamed as well as null: the intake wizard clears
 * a field by submitting `undefined`, but a value that has round-tripped as `""`
 * is not a name either, and a caller asking "can I print this?" wants one
 * answer rather than two.
 */
export function isNamedOrg(
  legalName: string | null | undefined,
): legalName is string {
  return typeof legalName === "string" && legalName.trim().length > 0;
}

/**
 * The organisation's name, or the unnamed label — always a printable string.
 *
 * Use this for anything a person reads: headings, option lists, `aria-label`s.
 * It is also what sorting and filtering key on, so an unnamed org sorts and
 * matches somewhere predictable instead of throwing on `null.toLowerCase()`.
 */
export function orgDisplayName(legalName: string | null | undefined): string {
  return isNamedOrg(legalName) ? legalName : UNNAMED_ORG_LABEL;
}
