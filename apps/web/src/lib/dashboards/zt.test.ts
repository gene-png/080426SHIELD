import { describe, expect, it } from "vitest";

import { pillarsByGap, radarData, type ZtPillar } from "./zt";

function pillar(p: Partial<ZtPillar>): ZtPillar {
  return {
    code: "ID",
    name: "Identity",
    capability_count: 5,
    answered_count: 5,
    current_pct: 50,
    current_label: "Initial",
    target_pct: 100,
    target_label: "Optimal",
    gap_pct: 50,
    weakest: [],
    ...p,
  };
}

const PILLARS: ZtPillar[] = [
  pillar({ name: "Identity", current_pct: 75, target_pct: 95, gap_pct: 20 }),
  pillar({ name: "Data", current_pct: 50, target_pct: 90, gap_pct: 40 }),
  pillar({ name: "Networks", current_pct: 68, target_pct: 90, gap_pct: 22 }),
];

describe("zt dashboard transforms", () => {
  it("radarData: current + target series in pillar order", () => {
    const r = radarData(PILLARS);
    expect(r.labels).toEqual(["Identity", "Data", "Networks"]);
    expect(r.current).toEqual([75, 50, 68]);
    expect(r.target).toEqual([95, 90, 90]);
  });

  it("radarData: null pct coerces to 0", () => {
    const r = radarData([pillar({ current_pct: null, target_pct: null })]);
    expect(r.current).toEqual([0]);
    expect(r.target).toEqual([0]);
  });

  it("pillarsByGap: largest gap first", () => {
    expect(pillarsByGap(PILLARS).map((p) => p.name)).toEqual([
      "Data",
      "Networks",
      "Identity",
    ]);
  });
});
