/**
 * The lowest level a client may TARGET, for each self-assessment ladder.
 *
 * ## One product rule, two ladders
 *
 * Level 1 is where an organization starts, not something it sets out to
 * reach, so neither target picker offers it. That is a single product
 * decision; it is expressed twice only because ZT counts in CISA/DoD *stages*
 * and CSF counts in *tiers*. They are declared side by side, under one
 * docstring, so that the next person to change one is looking at the other.
 *
 * ## Why these are HERE and not next to the pickers
 *
 * `MIN_TARGET_STAGE` was declared in `components/admin/zt/ZtWorkspace.tsx`
 * and honoured there, while three sibling filters spelled the same floor as a
 * bare `2` (#194):
 *
 *     ZtGapList.tsx          .filter((s) => s.stage >= 2)
 *     ZtSelfAssessment.tsx   catalog.stages.filter((s) => s.stage >= 2)
 *     CsfSelfAssessment.tsx  catalog.tiers.filter((t) => t.tier >= 2)
 *
 * **All four agreed, so there was no live defect** -- and the hazard was not
 * the disagreement, it was that nothing could ever cause one to be noticed.
 * Raise the floor at the picker without the constant and `normalizeTarget`
 * can return a stage the dropdown no longer contains: a controlled `<select>`
 * whose `selectedIndex` is `-1` renders BLANK, with no error, no refusal and
 * nothing in a log. The failure is silent by construction.
 *
 * A client surface must not import from an admin component either, so
 * `ZtSelfAssessment` and `CsfSelfAssessment` had no honest way to reach the
 * existing constant. This module is the shared home that gives them one.
 *
 * ## This floor is the WEB's, not the API's
 *
 * Stated because the obvious assumption is wrong and would be load-bearing.
 * `routes/zt.py` validates a target only against the framework's own ladder
 * -- `{framework} has stages 1-{max}; target_stage={n} is not one of them.`
 * -- so the API ACCEPTS stage 1, and `app/zt/scoring.py` exports
 * `DEFAULT_TARGET_STAGE` but no minimum at all. Nothing on the Python side
 * mirrors these values, so there is no cross-language window to keep closed
 * and no server-side test that could go red if they changed.
 *
 * That cuts both ways, and it is the reason this file exists rather than a
 * comment: the web layer is the ONLY place this rule is written down, so a
 * single home is the whole of its enforcement.
 */

/** ZT (CISA ZTMM 2.0 and DoD ZTRA). Stage 1 is a starting point, not a goal. */
export const MIN_TARGET_STAGE = 2;

/** NIST CSF 2.0. Tier 1 ("Partial") is a starting point, not a goal. */
export const MIN_TARGET_TIER = 2;
