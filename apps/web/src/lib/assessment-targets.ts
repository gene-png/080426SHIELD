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
 * ## What this module is, and what it is NOT
 *
 * **It is one home for the five web sites that COMPARE against the floor.** It
 * is not the only place the rule is written down, and an earlier version of
 * this docstring claimed it was — "a single home is the whole of its
 * enforcement", which was false when written. The remaining spellings are
 * enumerated below rather than glossed, because an overstated scope here is
 * the sentence a reader checks instead of grepping.
 *
 * Wired to this module:
 *
 *     ZtWorkspace.normalizeTarget        .filter((s) => s >= MIN_TARGET_STAGE)
 *     ZtGapList                          .filter((s) => s.stage >= …)
 *     ZtSelfAssessment                   catalog.stages.filter(…)
 *     CsfSelfAssessment                  catalog.tiers.filter(…)
 *     CsfWorkspace.normalizeTarget       the floor half of its range check
 *
 * Also wired, since #406 — and these are where the client FIRST chooses a
 * target, so they are the sites that matter most:
 *
 *     lib/intake/types.ts CSF_TARGET_TIERS   CSF_TIERS.filter(t => t.value >= …)
 *     lib/intake/types.ts ZT_TARGET_STAGES   both variants, same filter
 *
 * They encoded the floor by OMISSION — the arrays simply opened at
 * `{ value: 2 }` — and escaped the sweep that produced this module because
 * that sweep grepped for a COMPARISON against a ladder noun, and **a floor
 * expressed by omission from an option list contains no comparison at all**.
 * Worth knowing before trusting any future sweep of this rule: it has to look
 * for the number 2 used as a lower bound however expressed, including by
 * absence.
 *
 * ## The API carries its own copy of this floor
 *
 * **Stated because this docstring once claimed the opposite**, and the false
 * claim was the load-bearing one: it read "nothing on the Python side mirrors
 * these values, so there is no cross-language window to keep closed". How that
 * claim was produced is the useful part: `routes/zt.py` and `app/zt/scoring.py`
 * were both read, and both are individually accurate — the route validates only
 * against the framework's ladder and accepts stage 1, and the scoring module
 * exports a default with no minimum. **A per-file check was then published as a
 * system-wide negative**, which is the certificate-over-the-wrong-proposition
 * shape: the commands proved something true and adjacent to the sentence they
 * were cited for.
 *
 * The window is real. As of #406 it is **one declaration wide** rather than
 * four bounds wide: `apps/api/app/assessment_targets.py` is this file's Python
 * mirror, and `routes/intake.py::_validate_targets` is the single place that
 * compares against it. The four `Field(..., ge=2, le=4)` bounds that used to
 * carry the rule are gone — they were refused as a raw `schema_*` 422, message
 * `"Request validation failed."`, with no client copy behind it, on the surface
 * where a client first picks a target.
 *
 * **What closes that window, and what it does not do.** Each language's own
 * suite spells the number and names the other file in its failure message —
 * `test_intake_target_floor.py` and `target-options-are-derived.test.ts`. So a
 * unilateral change goes RED on the side that made it. It does NOT prove the
 * two agree: neither container mounts the other's tree, so no test can read
 * across. Tracked in **#422**; `SCHEMA_REASON_PREFIX` in
 * `lib/describe-save-error.ts` settled the identical problem the same way.
 *
 * ## Why the constants live HERE rather than in a component
 *
 * `MIN_TARGET_STAGE` was declared in `components/admin/zt/ZtWorkspace.tsx`
 * and honoured there, while sibling filters spelled the same floor as a bare
 * `2` (#194). All of them agreed, so there was no live defect — and the hazard
 * was not the disagreement, it was that nothing could ever cause one to be
 * noticed. Raise the floor at the picker without the constant and
 * `normalizeTarget` can return a stage the dropdown no longer contains: a
 * controlled `<select>` whose `selectedIndex` is `-1` renders BLANK, with no
 * error, no refusal and nothing in a log.
 *
 * **The reason is bundle shape, NOT an import-direction rule**, and the first
 * version of this docstring got that wrong in a way worth recording: it said a
 * client surface must not import from an admin component, so the pickers "had
 * no honest way to reach the existing constant". Both of them already do —
 * `ZtSelfAssessment.tsx` imports `@/components/admin/zt/ZtStagePicker` and
 * `CsfSelfAssessment.tsx` imports `@/components/admin/csf/CsfQuestionnaire`.
 * A reader enforcing the stated convention would have filed work to unpick two
 * existing, working imports.
 *
 * The real reason is narrower and survives: importing a constant out of a
 * component module drags that whole component — and its own imports — into
 * every bundle that wants the number. A two-line module does not.
 */

/** ZT (CISA ZTMM 2.0 and DoD ZTRA). Stage 1 is a starting point, not a goal. */
export const MIN_TARGET_STAGE = 2;

/** NIST CSF 2.0. Tier 1 ("Partial") is a starting point, not a goal. */
export const MIN_TARGET_TIER = 2;
