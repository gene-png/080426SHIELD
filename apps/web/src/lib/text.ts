/** Small text helpers shared across forms. */

/** Split user-entered text into lines, tolerating CRLF from Windows paste. */
export function splitLines(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}
