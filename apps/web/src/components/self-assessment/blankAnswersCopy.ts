/**
 * #1173: the warning a client sees on "Submit for review" while answers are
 * still blank. Approved verbatim on #736 (6206818759 item 4), the jump button
 * naming the function or pillar rather than its code. #1191: the middle
 * sentence is W-1191, approved verbatim on #736 (6216024281), because a blank
 * still counts against coverage and is reported as not scored.
 */

export type BlankAnswersNoun = "outcomes" | "capabilities";

export function blankAnswersMessage(
  blank: number,
  total: number,
  noun: BlankAnswersNoun,
): string {
  return `${blank} of ${total} ${noun} have no answer yet. Your consultant may score them, but any left blank are reported as not scored. Answer them now, or submit anyway.`;
}

export function goToAreaLabel(name: string, blank: number): string {
  return `Go to ${name} (${blank} blank)`;
}

export const SUBMIT_ANYWAY = "Submit anyway";
