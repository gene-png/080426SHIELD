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
