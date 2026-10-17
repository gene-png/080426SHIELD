/**
 * #1171: the CSF self-assessment's step-through copy. Approved on #736
 * (6207611148), naming functions rather than codes. The submit-lock sentence
 * (L1, `submitLocked`) and the locked button's title (L2,
 * `SUBMIT_LOCKED_TITLE`) are approved verbatim on #736 (6216024281).
 */

export function csfIntro(functions: number): string {
  return `This assessment covers ${functions} functions. Step through each one and rate every outcome for where your organization stands today. Each function needs at least one answer before you can submit. Use Previous and Next to move between them.`;
}

export function functionCounter(index: number, count: number): string {
  return `Function ${index} of ${count}`;
}

export function functionProgress(
  name: string,
  answered: number,
  total: number,
): string {
  return `${name}: ${answered} of ${total} answered`;
}

export const LAST_FUNCTION =
  "Last function. Review the others, then submit below.";

/** L1, approved (6216024281): Gene's lock (an answer in every function). */
export function submitLocked(names: string[]): string {
  return `Add at least one answer to every function before submitting. Still needs attention: ${names.join(", ")}.`;
}

/** L2, approved (6216024281): the locked button's title. */
export const SUBMIT_LOCKED_TITLE =
  "Answer at least one outcome in every function first.";
