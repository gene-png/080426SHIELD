/**
 * The lowest level a client may TARGET, for each self-assessment ladder.
 *
 * **THIS FILE IS BIND-MOUNTED BY `docker-compose.yml`** into the api container
 * (read-only, at `/web-parity/assessment-targets.ts`) so the api's parity test
 * can read it (#422). Rename or move it and you must change the mount too, or
 * that test fails hard -- by design, it never skips.
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
 * **It is one home for the web sites that COMPARE against the floor.** It
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
 * mirror, and `routes/intake.py::_validate_targets` compares against it. The
 * four `Field(..., ge=2, le=4)` bounds that used to carry the rule are gone —
 * they were refused as a raw `schema_*` 422, message
 * `"Request validation failed."`, with no client copy behind it, on the surface
 * where a client first picks a target.
 *
 * **`_validate_targets` is NOT the only comparison, and this docstring said it
 * was** — "the single place that compares against it", which is the kind of
 * true-sounding sentence that ends the next reader's search exactly where it
 * should have started. Two other routes write the same two columns, and since
 * #85 both refuse a below-floor target too: `routes/csf.py::submit_self_assessment`
 * through `_refuse_submitted_target_tier`, and `routes/zt.py::submit_self_assessment`.
 * Both resolvers report a target ALREADY stored as 1 as `client_below_floor`
 * rather than as the client's own choice. `assessment_targets.py` carries the
 * reasoning.
 *
 * **What closes the window, since #422.** The api's
 * `tests/unit/test_target_floor_parity.py` reads THIS file — through the
 * read-only mount, or in place on a CI checkout — and asserts the floors,
 * `BELOW_FLOOR_SOURCE` and `TARGET_SOURCE_NOTES` below equal the Python
 * ones, failing hard when it cannot read it. The per-side spelled literals
 * (`test_intake_target_floor.py`, `target-options-are-derived.test.ts`) still
 * turn a unilateral edit red on the side that made it; the parity test is what
 * proves the two agree. `SCHEMA_REASON_PREFIX` in `lib/describe-save-error.ts`
 * is NOT covered: it lives in another file, outside the one-file mount.
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

/**
 * #85: what a stored target BELOW the floor means, in one place.
 *
 * The API's resolvers (`csf/gap.py::resolve_target_tier`,
 * `zt/scoring.py::resolve_target_stage`) report a stored 1 as
 * `client_below_floor` and fall back to the engine default: Tier/Stage 1 is a
 * level the ladder has and not a target. The dashboards render that source
 * with these strings, and the consultant workspaces render the SAME strings
 * beside the target select, so the screen that keeps 3 selected says why.
 * Declared here rather than in a dashboard module so the workspace does not
 * pull a dashboard into its bundle (the reason the floors live here too).
 *
 * #783: the two notes are also in the client's DOCUMENTS. They are rows of
 * `TARGET_SOURCE_NOTES` below, which the api's copy is asserted equal to
 * (#422).
 */
export const BELOW_FLOOR_SOURCE = "client_below_floor";

/**
 * #783: why the engagement target is a default, per resolver source, in the
 * words the client reads on BOTH the dashboard and the deliverable. The ONE
 * table: `dashboards/csf.ts::targetFaultNote`, `dashboards/zt.ts::targetFault`
 * and the two below-floor notes below all derive from it.
 *
 * The api has the same table, `TARGET_SOURCE_NOTES` in
 * `apps/api/app/assessment_targets.py`, which its deliverables state; the
 * api's `test_target_floor_parity.py` reads THIS declaration through the mount
 * and asserts the two are equal, so a reword here alone goes red there.
 *
 * Kept a plain object of double-quoted string literals so that parser can
 * read it: no computed keys, no spreads, no references. `unrecognised` is not
 * a resolver source; it is what a source this build does not know reads, so an
 * unknown value still says something true rather than nothing.
 */
export const TARGET_SOURCE_NOTES = {
  tier: {
    default: "no tier chosen at intake",
    client_out_of_range: "the tier on file is not one CSF has",
    client_below_floor: "the tier on file is a starting point, not a target",
    client_unparseable: "the tier on file could not be read",
    unrecognised: "the tier on file was not usable",
  },
  stage: {
    default: "no stage chosen at intake",
    client_out_of_range: "the stage on file is not one this framework has",
    client_below_floor: "the stage on file is a starting point, not a target",
    client_unparseable: "the stage on file could not be read",
    unrecognised: "the stage on file was not usable",
  },
} as const;

/**
 * Why the stored target could not be used, for one rung, or null when the
 * client's own choice stands. Own-property lookup only: `source` is API data,
 * and a value like "toString" must read as unrecognised, not as a function.
 */
export function targetSourceNote(
  rung: keyof typeof TARGET_SOURCE_NOTES,
  source: string,
): string | null {
  if (source === "client") return null;
  const notes: Record<string, string> = TARGET_SOURCE_NOTES[rung];
  return Object.prototype.hasOwnProperty.call(notes, source)
    ? notes[source]
    : notes.unrecognised;
}

export const TIER_BELOW_FLOOR_NOTE =
  TARGET_SOURCE_NOTES.tier[BELOW_FLOOR_SOURCE];
export const STAGE_BELOW_FLOOR_NOTE =
  TARGET_SOURCE_NOTES.stage[BELOW_FLOOR_SOURCE];

/**
 * True when a stored engagement target is a real level below `floor` -- the
 * case the API resolves as `client_below_floor`. Mirrors the resolvers'
 * order: a non-number or a fraction is a different fault, and 0 or less is
 * off the ladder rather than below the floor.
 */
export function isBelowTargetFloor(value: unknown, floor: number): boolean {
  return (
    typeof value === "number" &&
    Number.isInteger(value) &&
    value >= 1 &&
    value < floor
  );
}
