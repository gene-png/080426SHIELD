import { describe, expect, it } from "vitest";

import {
  matrixGrid,
  tierColor,
  tierMix,
  titleCase,
  type RiskMatrixCell,
} from "./risk";

function cells(): RiskMatrixCell[] {
  const out: RiskMatrixCell[] = [];
  const lk = ["very_low", "low", "medium", "high", "very_high"];
  const im = ["negligible", "minor", "moderate", "major", "catastrophic"];
  for (const l of lk)
    for (const i of im)
      out.push({ likelihood: l, impact: i, tier: "low", count: 0 });
  return out;
}

describe("risk dashboard transforms", () => {
  it("matrixGrid: 5x5, rows high→low likelihood", () => {
    const g = matrixGrid(cells());
    expect(g).toHaveLength(5);
    expect(g[0]).toHaveLength(5);
    expect(g[0][0].likelihood).toBe("very_high"); // top row
    expect(g[4][0].likelihood).toBe("very_low"); // bottom row
    expect(g[0][4].impact).toBe("catastrophic"); // top-right cell
  });

  it("matrixGrid: places counts in the right cell", () => {
    const c = cells();
    c.find(
      (x) => x.likelihood === "very_high" && x.impact === "catastrophic",
    )!.count = 3;
    c.find(
      (x) => x.likelihood === "very_high" && x.impact === "catastrophic",
    )!.tier = "critical";
    const g = matrixGrid(c);
    expect(g[0][4].count).toBe(3);
    expect(g[0][4].tier).toBe("critical");
  });

  it("tierMix: severity order, drops empty tiers", () => {
    const mix = tierMix({ critical: 2, medium: 1, negligible: 0 });
    expect(mix.map((m) => m.label)).toEqual(["Critical", "Medium"]);
    expect(mix[0].value).toBe(2);
  });

  it("tierColor + titleCase", () => {
    expect(tierColor("critical")).toBe("#ef4444");
    expect(titleCase("very_high")).toBe("Very High");
  });
});
