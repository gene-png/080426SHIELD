import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AttackDashboardData } from "@/lib/dashboards/attack";

/**
 * The released date is an INSTANT. Formatted in the viewer's zone, a release
 * at 02:00 UTC read as the day before for anyone west of UTC, so one release
 * read as different days to different readers. It is pinned to UTC.
 *
 * The runner's own zone is UTC, where a pinned formatter and an unpinned one
 * print the same thing, so these tests set TZ BEFORE importing the module (the
 * formatter is built at import) and assert the zone really took. Without that
 * precondition they would pass against the defect.
 *
 * ATT&CK is tested through its own dashboard: it used to carry a PRIVATE copy
 * of the badge and formatter, so pinning the shared one left it unpinned
 * while re-testing the other four came back clean.
 */

const savedTz = process.env.TZ;

afterEach(() => {
  if (savedTz === undefined) delete process.env.TZ;
  else process.env.TZ = savedTz;
  vi.resetModules();
});

async function inZone<T>(tz: string, load: () => Promise<T>): Promise<T> {
  process.env.TZ = tz;
  vi.resetModules();
  // The precondition: the zone took. If it did not, both halves of every
  // assertion below would be computed in UTC and agree for nothing.
  expect(Intl.DateTimeFormat().resolvedOptions().timeZone).toBe(tz);
  return load();
}

// 02:00 UTC on the 23rd is the 22nd in Los Angeles; 22:30 UTC on the 23rd is
// the 24th at UTC+14. Either direction would move an unpinned date.
const EARLY = "2026-09-23T02:00:00Z";
const LATE = "2026-09-23T22:30:00Z";

describe("formatDate (the shared released badge)", () => {
  it("prints the UTC day west of UTC", async () => {
    const { formatDate } = await inZone(
      "America/Los_Angeles",
      () => import("./shared"),
    );
    expect(formatDate(EARLY)).toBe("Sep 23, 2026");
  });

  it("prints the UTC day east of UTC", async () => {
    const { formatDate } = await inZone(
      "Pacific/Kiritimati",
      () => import("./shared"),
    );
    expect(formatDate(LATE)).toBe("Sep 23, 2026");
  });
});

function attackData(releasedAt: string): AttackDashboardData {
  return {
    service_id: "svc-1",
    service_title: "Atlas ATT&CK",
    released_at: releasedAt,
    deliverable_version: 2,
    rollup: {
      total_evaluated: 0,
      covered: 0,
      partial: 0,
      gap: 0,
      not_applicable: 0,
      coverage_pct: 0,
      by_tactic: [],
    },
    techniques: [],
  };
}

describe("AttackDashboard's released badge", () => {
  it("prints the UTC day west of UTC, like the other four dashboards", async () => {
    const { AttackDashboard } = await inZone(
      "America/Los_Angeles",
      () => import("./attack/AttackDashboard"),
    );
    render(<AttackDashboard data={attackData(EARLY)} />);
    expect(screen.getByText(/Released Sep 23, 2026 · v2/)).toBeInTheDocument();
  });
});
