/**
 * #889: a cited tool that is not in the client's CURRENT security tool list.
 * The API decides which (`app/attack/subset_drift.py`, the same check the
 * admin workspace and finalize read) and sends the names it marks; an absent
 * list means nothing could be checked: the client has no Tech Debt list, or
 * none with a security tool (R4), and the API's sentence says which.
 *
 * The mark is COPIED from `app/attack/subset_drift.py` (`OUTSIDE_MARK`),
 * because the deliverable and these screens must print the same words. Change
 * both. Copy approved verbatim (advisor, #736 comment 6090360421).
 */

/** C3: after " (unconfirmed)" and after the retirement mark. */
export const OUTSIDE_MARK = " (not in the security tool list)";

/** C2: beside the marks on any screen that reads the list LIVE. A released
 *  document keeps the list as it stood at finalize. */
export const CURRENT_LIST_NOTE =
  "Security tool list checks reflect the client's current security tool list.";

/** C7: on the home card, beside an ATT&CK uncovered total when a released
 *  assessment has a Covered or Partial row (effective status) crediting such
 *  a tool. The total sums Gap only, so that row is NOT in it: the total may
 *  be understated. A Gap row crediting one is already in the total and does
 *  not raise it (`attack_covered_relies_on_outside_tool`). */
export const HOME_CARD_NOTE =
  "Some techniques counted as covered rely on a tool that is not in the client's current security tool list, so this total may be understated.";

/** #1011: on the home card, beside an ATT&CK figure whose tools could not be
 *  checked (`attack_subset_not_checked_reason`), so "not checked" no longer
 *  reads as "checked, none found". Copy strings 1 to 3, approved verbatim
 *  (advisor, #736 comment 6094262391, on the plan at 6093958175). Neutral:
 *  unchecked is unknown, not found, so no "may be understated". String 1 is
 *  C5's sense ("no_list" and "discarded"), string 2 C5b's ("empty"). */
export const HOME_CARD_NOT_CHECKED_NO_LIST =
  "Tools credited for techniques counted as covered were not checked against a security tool list, because the client has none.";
export const HOME_CARD_NOT_CHECKED_EMPTY =
  "Tools credited for techniques counted as covered were not checked against a security tool list, because the client's security tool list has no security tools.";
/** String 3: a reason this build does not know (an API newer than the page). */
export const HOME_CARD_NOT_CHECKED_FALLBACK =
  "Tools credited for techniques counted as covered were not checked against a security tool list.";

/** The not-checked line for `reason`, or null when there is none to state
 *  (checked, or no figure: the API sends null). An unknown value logs an error
 *  and falls back to string 3 rather than throwing: the home page must render. */
export function homeCardNotCheckedNote(
  reason: string | null | undefined,
): string | null {
  if (reason == null) return null;
  if (reason === "no_list" || reason === "discarded") {
    return HOME_CARD_NOT_CHECKED_NO_LIST;
  }
  if (reason === "empty") return HOME_CARD_NOT_CHECKED_EMPTY;
  console.error("[home] unknown ATT&CK not-checked reason", reason);
  return HOME_CARD_NOT_CHECKED_FALLBACK;
}

export function outsideMark(
  tool: string,
  outside: readonly string[] | undefined,
): string {
  return outside?.includes(tool) ? OUTSIDE_MARK : "";
}

/** True when at least one tool is marked, which is when `CURRENT_LIST_NOTE`
 *  shows (D-105's pattern: the freshness line sits beside the labels). */
export function anyOutsideMark(
  outside: readonly string[] | undefined,
): boolean {
  return outside != null && outside.length > 0;
}
