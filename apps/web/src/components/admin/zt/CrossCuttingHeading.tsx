import type { CatalogCapability } from "@/lib/zt/types";

/** The approved sub-heading copy (#838 comment 5982917066). */
export const CROSS_CUTTING = "Cross-cutting";

/**
 * True for the first cross-cutting row of a pillar's list. CISA ZTMM 2.0
 * tabulates each pillar's Visibility and Analytics, Automation and
 * Orchestration and Governance rows after its functions (#838), and the
 * catalog keeps that order, so the heading goes once, before the first.
 */
export function startsCrossCutting(
  all: readonly CatalogCapability[],
  i: number,
): boolean {
  return (
    all[i]?.kind === "cross_cutting" && all[i - 1]?.kind !== "cross_cutting"
  );
}

/** The sub-heading itself, as a list item of the pillar's list. */
export function CrossCuttingHeading() {
  return (
    <li className="pt-2">
      <h4 className="text-xs font-semibold uppercase tracking-[0.12em] text-ink-tertiary">
        {CROSS_CUTTING}
      </h4>
    </li>
  );
}
