/**
 * #1173: the warning a client sees on "Submit for review" while answers are
 * still blank.
 *
 * PLACEHOLDER COPY, pending Gene's verbatim approval. These are the strings
 * proposed on #736 (6205190541); the approved text replaces them here, in one
 * commit, and the tests that quote them move with it.
 */

export type BlankAnswersNoun = "outcomes" | "capabilities";

export function blankAnswersMessage(
  blank: number,
  total: number,
  noun: BlankAnswersNoun,
): string {
  return `${blank} of ${total} ${noun} have no answer yet. Blank answers are left out of your results. Answer them now, or submit anyway.`;
}

export function goToAreaLabel(code: string, blank: number): string {
  return `Go to ${code} (${blank} blank)`;
}

export const SUBMIT_ANYWAY = "Submit anyway";
