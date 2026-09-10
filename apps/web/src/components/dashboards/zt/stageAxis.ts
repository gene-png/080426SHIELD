import type { ZtFramework } from "@/lib/zt/types";

/**
 * The stage names a Zero Trust maturity legend should carry, per framework.
 *
 * ## Why this is not inline in the component
 *
 * It was, and it was CISA's four stages under every framework — so a DoD ZTRA
 * client read their maturity against a four-stop scale labelled with another
 * framework's names, "Optimal" among them, which is not a DoD stage at all.
 * That is the label #125 removed from the intake UI, still rendering on the
 * client's own results page. Filed as #208.
 *
 * The bars were never wrong: `current_pct` / `target_pct` are normalised
 * server-side against `level_count(framework)`, so the geometry was right and
 * only the legend lied. Nothing looked broken, and nothing caught it.
 *
 * ## Why a Record rather than a switch or a lookup with a default
 *
 * `ZtFramework` is a closed union this codebase owns, so `Record<ZtFramework,
 * …>` makes adding a third framework WITHOUT adding its stage names a compile
 * error rather than a silent staleness. The issue asks for derivation over
 * enumeration for exactly that reason; this is the enumeration that cannot go
 * stale quietly, which is the same move as the exhaustive `Record<Outcome, …>`
 * used elsewhere in this repo.
 *
 * Source of truth is `app/zt/maturity.py` — `stage_label` and `level_count`.
 * These are its outputs, not a second opinion about them.
 */
const STAGE_LABELS: Record<ZtFramework, readonly string[]> = {
  cisa_ztmm_2_0: ["Traditional", "Initial", "Advanced", "Optimal"],
  dod_ztra: ["Not Started", "Target", "Advanced"],
};

/**
 * The stage axis for a framework, or `null` when the framework is unrecognised.
 *
 * **`null` is deliberate and is the whole point.** `ZtDashboardData.framework`
 * is typed `string`, so the compiler cannot rule out a value this file has
 * never heard of — a new framework shipped server-side, or a payload from an
 * older release. Falling back to *some* axis in that case is the defect being
 * fixed here, one framework further on.
 *
 * A caller that gets `null` renders no legend. The bar and the target marker
 * are unaffected, because they are positioned from percentages the server
 * already normalised — so the client still sees where they are and where they
 * are going, just without stage names. **Absent beats wrong**: a missing
 * legend is visible to the reader, and a legend from the wrong framework is
 * not.
 *
 * Returns a fresh array so a caller that sorts or reverses in place cannot
 * corrupt every later render.
 */
export function stageAxis(framework: string): readonly string[] | null {
  if (!Object.prototype.hasOwnProperty.call(STAGE_LABELS, framework)) {
    return null;
  }
  return [...STAGE_LABELS[framework as ZtFramework]];
}
