import type { CapabilityItem } from "./types";

/**
 * Bundle components on the admin side: the web statement of the rule
 * `apps/api/app/tech_debt/components.py` holds (for #935).
 *
 * A row with `parent_item_id` set is a named part of a split bundle, such as
 * Defender for Endpoint inside Microsoft 365 E5. The bundle row keeps the whole
 * licence value, so a part is not a capability of its own and not a cost. The
 * client dashboard and the deliverable count source items through the API
 * module; the workspace counts them through this one, so the two agree.
 */
export function isComponent(
  item: Pick<CapabilityItem, "parent_item_id">,
): boolean {
  return item.parent_item_id !== null && item.parent_item_id !== undefined;
}

/** The rows that came from the upload, or were added as tools of their own. */
export function sourceItems<T extends Pick<CapabilityItem, "parent_item_id">>(
  items: readonly T[],
): T[] {
  return items.filter((it) => !isComponent(it));
}

/**
 * TD-10 (for #1048): the source rows with no recorded cost, which every cost
 * total leaves out. The web statement of `no_cost_items` in
 * `apps/api/app/tech_debt/overlap.py`: a recorded $0 is a cost, and a split
 * bundle's part carries none of its own.
 */
export function noCostItems<
  T extends Pick<CapabilityItem, "parent_item_id" | "annual_cost_usd">,
>(items: readonly T[]): T[] {
  return sourceItems(items).filter(
    (it) => it.annual_cost_usd === null || it.annual_cost_usd === undefined,
  );
}

/**
 * "{n} tools have no cost; total excludes them", or null at 0. Approved
 * verbatim on #736 (6115773247; strings in 6115177462), with its singular. A count that is not a
 * positive whole number (an API older than the field) says nothing rather
 * than "undefined tools".
 */
export function noCostSentence(n: number): string | null {
  if (!Number.isInteger(n) || n <= 0) return null;
  return n === 1
    ? "1 tool has no cost; total excludes it"
    : `${n} tools have no cost; total excludes them`;
}
