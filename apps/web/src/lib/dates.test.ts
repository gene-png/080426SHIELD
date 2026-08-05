import { describe, expect, it } from "vitest";

import { formatDateOnly } from "./dates";

/**
 * A deadline entered as 2027-06-30 was rendering as 6/29/2027 for anyone west
 * of UTC (found on a America/Chicago box in the 2026-08-04 review). The stored
 * value is correct; the bug is treating a calendar date as a UTC timestamp and
 * then formatting it in local time.
 */
describe("formatDateOnly", () => {
  it("keeps a bare calendar date on its own day", () => {
    expect(formatDateOnly("2027-06-30")).toBe("6/30/2027");
  });

  it("keeps a UTC-midnight timestamp on its own day", () => {
    // What the API actually serialises for a date-only column.
    expect(formatDateOnly("2027-06-30T00:00:00Z")).toBe("6/30/2027");
    expect(formatDateOnly("2027-06-30 00:00:00+00")).toBe("6/30/2027");
  });

  it("does not shift across a new year", () => {
    expect(formatDateOnly("2027-01-01")).toBe("1/1/2027");
    expect(formatDateOnly("2026-12-31T00:00:00Z")).toBe("12/31/2026");
  });

  it("returns null for an empty or unusable value rather than 'Invalid Date'", () => {
    expect(formatDateOnly(null)).toBeNull();
    expect(formatDateOnly("")).toBeNull();
    expect(formatDateOnly("not-a-date")).toBeNull();
  });
});
