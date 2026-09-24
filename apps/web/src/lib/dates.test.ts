import { afterEach, describe, expect, it, vi } from "vitest";

import { formatDateOnly, formatInstantUtc } from "./dates";

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

/**
 * Instants -- released, finalized, submitted -- are formatted in UTC and SAY
 * so, on every surface that shows them. Round 1 of review on the timezone
 * branch: pinning the admin table to UTC while the admin card beside it still
 * used the viewer's zone made one release read as two days to one consultant.
 */
describe("formatInstantUtc", () => {
  const savedTz = process.env.TZ;
  afterEach(() => {
    if (savedTz === undefined) delete process.env.TZ;
    else process.env.TZ = savedTz;
    vi.resetModules();
  });

  it("prints the UTC day and names the zone, wherever the viewer is", async () => {
    // The formatter is built at IMPORT, so the zone is set first and the module
    // re-imported: imported statically, it was built in the runner's UTC and
    // this passed with the pin removed (caught by red-on-revert).
    process.env.TZ = "America/Los_Angeles";
    vi.resetModules();
    // The precondition: the zone took, or this proves nothing in a UTC runner.
    expect(Intl.DateTimeFormat().resolvedOptions().timeZone).toBe(
      "America/Los_Angeles",
    );
    const { formatInstantUtc: fresh } = await import("./dates");
    const text = fresh("2026-09-23T01:30:00Z");
    // The month is SPELLED: "9/10/2026" reads as 9 October to a day-first
    // reader, and the table and dashboards already say "Sep 23, 2026".
    expect(text).toMatch(/Sep 23, 2026/);
    expect(text).toMatch(/UTC/);
  });

  it("returns an em dash for no value and the raw text for a bad one", () => {
    expect(formatInstantUtc(null)).toBe("—");
    expect(formatInstantUtc("not-a-date")).toBe("not-a-date");
  });
});
