/**
 * #889: a cited tool that is not in the client's CURRENT security tool list.
 * The API decides which (`app/attack/subset_drift.py`, the same check the
 * admin workspace and finalize read) and sends the names it marks; an absent
 * list means nothing could be checked (the client has none).
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
 *  assessment credits such a tool. The total sums Gap only, so a row that
 *  credits one counts as covered and is NOT in it: the total may be low. */
export const HOME_CARD_NOTE =
  "Some techniques counted as covered rely on a tool that is not in the client's current security tool list, so this total may be understated.";

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
