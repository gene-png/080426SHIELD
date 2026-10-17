import { describe, expect, it } from "vitest";

import { pillarsByGap, radarData, type ZtPillar } from "./zt";

// #1183: stage 1 is now 0%, so a pillar with nothing scored (null) must not be
// plotted at 0, where a pillar scored at the lowest stage sits.
function pillar(p: Partial<ZtPillar>): ZtPillar {
  return {
    code: "ID",
    name: "Identity",
    capability_count: 7,
    answered_count: 7,
    current_pct: 33.3,
    current_label: "Initial",
    target_pct: 100,
    target_label: "Optimal",
    gap_pct: 66.7,
    weakest: [],
    ...p,
  };
}

describe("radarData with an unscored pillar (#1183)", () => {
  it("carries null for a pillar with no score, and 0 for one scored at stage 1", () => {
    const r = radarData([
      pillar({ name: "Identity", current_pct: 0 }),
      pillar({
        name: "Data",
        answered_count: 0,
        current_pct: null,
        current_label: "Unscored",
      }),
    ]);
    expect(r.labels).toEqual(["Identity", "Data"]);
    expect(r.current).toEqual([0, null]);
  });
});

describe("pillarsByGap with an unscored pillar (#1183)", () => {
  it("puts a pillar with an unknown gap last, not first", () => {
    const names = pillarsByGap([
      pillar({ name: "Data", current_pct: null, gap_pct: null }),
      pillar({ name: "Identity", gap_pct: 66.7 }),
      pillar({ name: "Networks", gap_pct: 10 }),
      // A scored pillar already at its target (gap 0.0) still outranks an
      // unscored one: null must not be read as 0, or the stable sort keeps
      // Data above it.
      pillar({ name: "Devices", gap_pct: 0 }),
    ]).map((p) => p.name);
    expect(names).toEqual(["Identity", "Networks", "Devices", "Data"]);
  });
});
