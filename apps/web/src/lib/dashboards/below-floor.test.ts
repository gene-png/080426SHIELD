import { describe, expect, it } from "vitest";

import { isBelowTargetFloor } from "@/lib/assessment-targets";

import { targetFaultNote } from "./csf";
import { targetNote, type ZtDashboardData } from "./zt";

/**
 * #85: a stored engagement target of 1 resolves as `client_below_floor`.
 *
 * Tier/Stage 1 is a level the ladder HAS, so the out-of-range copy ("not one
 * CSF has") would be false of it, and the unknown-source fallback ("was not
 * usable") would say nothing about why. The expected strings are the copy the
 * coordinator approved on #85, written out here rather than imported.
 */

function zt(p: Partial<ZtDashboardData>): ZtDashboardData {
  return {
    service_id: "s",
    unusable_target_codes: [],
    service_title: "Atlas — Zero Trust",
    released_at: "2026-09-06T00:00:00Z",
    deliverable_version: 1,
    framework: "cisa_ztmm_2_0",
    framework_label: "CISA ZTMM 2.0",
    current_label: "Initial",
    current_pct: 50,
    target_label: "Advanced",
    target_pct: 75,
    target_stage: 3,
    target_stage_source: "client_below_floor",
    target_frozen_at: "2026-09-06T00:00:00Z",
    engagement_target_capability_count: 37,
    total_gap_count: 37,
    largest_gap_pillar: "Identity",
    largest_gap_pct: 50,
    pillars: [],
    ...p,
  };
}

describe("a stored target below the floor (#85)", () => {
  it("the CSF dashboard names it as a starting point, not a target", () => {
    expect(targetFaultNote("client_below_floor")).toBe(
      "the tier on file is a starting point, not a target",
    );
  });

  it("the ZT dashboard names it as a starting point, not a target", () => {
    expect(targetNote(zt({}))).toBe(
      "Default target — the stage on file is a starting point, not a target.",
    );
  });

  it("the ZT dashboard still names it when every capability carried its own target", () => {
    // The fully-overridden branch appends only a FAILED client choice; a
    // below-floor 1 is one, and must not be swallowed there either.
    expect(targetNote(zt({ engagement_target_capability_count: 0 }))).toBe(
      "Per-capability targets from your assessment — the stage on file is a starting point, not a target.",
    );
  });

  it("isBelowTargetFloor: only a whole level from 1 up to the floor", () => {
    expect(isBelowTargetFloor(1, 2)).toBe(true);
    for (const v of [
      2,
      3,
      0,
      -1,
      1.5,
      "1",
      null,
      undefined,
      true,
      Number.NaN,
    ]) {
      expect(isBelowTargetFloor(v, 2), String(v)).toBe(false);
    }
  });
});
