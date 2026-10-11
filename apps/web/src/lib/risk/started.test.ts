import { describe, expect, it } from "vitest";

import { startedDate, startedLine } from "./started";

/**
 * #896 review B1: the "{d Mon yyyy}" part of the approved line, in UTC
 * (coordinator, on Q2). Expected values written from the format, not computed
 * by the code under test.
 */
describe("startedDate (#896 B1)", () => {
  it("formats d Mon yyyy with no leading zero", () => {
    expect(startedDate("2026-10-03T12:00:00Z")).toBe("3 Oct 2026");
    expect(startedDate("2026-01-21T00:00:00+00:00")).toBe("21 Jan 2026");
  });

  it("uses the UTC date, not the viewer's", () => {
    expect(startedDate("2026-10-03T23:30:00+00:00")).toBe("3 Oct 2026");
    expect(startedDate("2026-10-03T22:30:00-05:00")).toBe("4 Oct 2026");
    // A viewer west of UTC, where it is still the 3rd: the test runner is
    // usually on UTC, so without this a local-time reading would pass too.
    const before = process.env.TZ;
    process.env.TZ = "America/New_York";
    try {
      expect(new Date("2026-10-04T02:00:00Z").getDate()).toBe(3);
      expect(startedDate("2026-10-04T02:00:00Z")).toBe("4 Oct 2026");
    } finally {
      if (before === undefined) delete process.env.TZ;
      else process.env.TZ = before;
    }
  });

  it("refuses a value that is not a date rather than printing one", () => {
    expect(() => startedDate("not a date")).toThrow(/not a date/);
  });
});

/**
 * The approved line (advisor, #736 6046898402): "Started {d Mon yyyy},
 * version {n}, {panel word}", the Inputs panel's word unchanged. Each
 * expected string is written out by hand from the ruling and the panel's
 * words in `lib/risk/inputs.ts`.
 */
describe("startedLine (#896 B1)", () => {
  const row = (status: string, version: number) => ({
    service_id: "s",
    title: "Acme — Zero Trust",
    started_at: "2026-10-03T12:00:00Z",
    status,
    version,
  });

  it("matches the advisor's example", () => {
    expect(startedLine(row("released", 2))).toBe(
      "Started 3 Oct 2026, version 2, released",
    );
  });

  it("uses the Inputs panel's words for every other state", () => {
    expect(startedLine(row("draft", 1))).toBe(
      "Started 3 Oct 2026, version 1, in progress (draft)",
    );
    expect(startedLine(row("submitted", 1))).toBe(
      "Started 3 Oct 2026, version 1, submitted, not yet released",
    );
    expect(startedLine(row("approved", 3))).toBe(
      "Started 3 Oct 2026, version 3, approved, not yet released",
    );
  });
});
