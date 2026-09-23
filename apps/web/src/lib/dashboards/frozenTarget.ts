/**
 * Whether a dashboard's figures were computed against the target its RELEASED
 * REPORT was rendered against, in the client's words (#209).
 *
 * ONE wording for both services, in its own module. A helper living inside
 * `zt.ts` and imported by `csf.ts` is how two surfaces come to describe one
 * fact differently: the next person edits "the ZT copy" and the CSF dashboard
 * changes underneath them, or they add a second sentence rather than reach
 * across. `CLAUDE.md` has this as a standing rule and this repo has paid for it
 * in `_gap_plan_caption` versus `targetNote` already.
 */

/**
 * The disclosure sentence, or `null` when there is nothing to disclose.
 *
 * #209: four surfaces resolved the engagement target LIVE on every request
 * while the released document held the number it was rendered with. Change the
 * intake target after release and the two disagree -- the PDF says "37 gaps at
 * target S4" and the dashboard beside it says something else, computed from the
 * same approved answers. Both internally consistent, and one is a number the
 * client never contracted for.
 *
 * **NULL RETURNS NOTHING, AND THAT ASYMMETRY IS THE POINT.** A non-null
 * `target_frozen_at` means the figures agree with the released report by
 * construction, which is the contract being honoured -- printing a sentence
 * about it on every dashboard would train every reader to skip the line, and
 * then the one case that matters is invisible for a reason nobody can see.
 * Silence here is a claim, and it is a true one.
 *
 * Never an imperative. A client cannot re-freeze a report from this page, and a
 * user-facing string naming an action has to name a control that exists and
 * works today.
 */
export function renderedAgainstNote(targetFrozenAt: string | null): string {
  return targetFrozenAt === null
    ? " These figures use your target as it stands today. Your released report" +
        " was rendered against the target on file at the time, so the two can" +
        " differ."
    : "";
}
