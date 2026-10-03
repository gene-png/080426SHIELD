/**
 * #686 (D-105): a Tech Debt tool marked Cut, or (since #810) "Cut, covered by
 * another tool", on an approved or released consolidation plan is a PLANNED
 * RETIREMENT; the API's `RETIRING_DISPOSITIONS` decides. It still counts toward ATT&CK
 * coverage, and every surface that shows it says so.
 *
 * The API decides the state (`app/attack/retirement.py`) and sends a map of
 * the cited tools it marks: `"planned_retirement"` or `"unknown"`. A tool
 * absent from the map is not retiring; an absent MAP means the client has no
 * consolidation plan, and nothing is marked.
 *
 * The suffixes are COPIED from `app/attack/retirement.py` (`PLANNED_MARK`,
 * `UNKNOWN_MARK`), because the deliverable and these screens must print the
 * same words. Change both.
 */

export const PLANNED_MARK = " (planned retirement)";
export const UNKNOWN_MARK = " (retirement status unknown)";

/** Beside the labels on any screen that reads the plan LIVE (#686, Q2): a
 *  released PDF keeps the plan as it stood at finalize. */
export const CURRENT_PLAN_NOTE =
  "Retirement labels reflect the current consolidation plan.";

export type ToolRetirement = Record<string, string> | null | undefined;

/** The suffix for `tool`, or "". An unrecognised state is shown as unknown
 *  rather than dropped: a value this build does not know is not "not
 *  retiring". */
export function retirementMark(tool: string, marks: ToolRetirement): string {
  const state = marks?.[tool];
  if (state === undefined) return "";
  return state === "planned_retirement" ? PLANNED_MARK : UNKNOWN_MARK;
}

export function withRetirementMark(
  tool: string,
  marks: ToolRetirement,
): string {
  return `${tool}${retirementMark(tool, marks)}`;
}

/** True when at least one label shows, which is when `CURRENT_PLAN_NOTE` is. */
export function anyRetirementMark(marks: ToolRetirement): boolean {
  return marks != null && Object.keys(marks).length > 0;
}
