import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RiskDashboard } from "./RiskDashboard";
import type { RiskDashboardData } from "@/lib/dashboards/risk";

/** #474: the client's dashboard names the baseline its findings used. */
function data(over: Partial<RiskDashboardData>): RiskDashboardData {
  return {
    ai_source: {
      state: "live",
      sentence: "AI suggestions in this assessment came from a live AI model.",
      live_runs: 1,
      fixture_runs: 0,
    },
    client_id: "00000000-0000-0000-0000-0000000000aa",
    released_at: "2026-10-04T00:00:00Z",
    version: 1,
    total_entries: 0,
    critical_count: 0,
    high_count: 0,
    tier_counts: {},
    axis_counts: {},
    action_counts: {},
    matrix: [],
    entries: [],
    entries_without_tier: 0,
    entries_without_axis: 0,
    entries_without_action: 0,
    ...over,
  };
}

describe("RiskDashboard baseline (#474)", () => {
  it("states the target the CSF findings were measured against", () => {
    render(
      <RiskDashboard
        data={data({
          targets: [
            {
              kind: "csf",
              framework: null,
              target: 4,
              source: "client",
              origin: "live_at_generate",
            },
          ],
          targets_recorded: true,
        })}
      />,
    );
    expect(screen.getByTestId("risk-targets-used").textContent).toBe(
      "NIST CSF findings are measured against target tier 4, the engagement target when this register was generated.",
    );
  });

  it("names each framework when CISA and DoD are both engaged", () => {
    render(
      <RiskDashboard
        data={data({
          targets: [
            {
              kind: "zt",
              framework: "cisa_ztmm_2_0",
              target: 4,
              source: "client",
              origin: "live_at_generate",
            },
            {
              kind: "zt",
              framework: "dod_ztra",
              target: 3,
              source: "default",
              origin: "live_at_generate",
            },
          ],
          targets_recorded: true,
        })}
      />,
    );
    expect(
      [...screen.getByTestId("risk-targets-used").querySelectorAll("p")].map(
        (p) => p.textContent,
      ),
    ).toEqual([
      "Zero Trust (CISA ZTMM 2.0) findings are measured against target stage 4, the engagement target when this register was generated.",
      "Zero Trust (DoD ZT Reference Architecture) findings are measured against target stage 3, SHIELD's default: no engagement target was set.",
    ]);
  });

  it("says the baseline was not recorded rather than saying nothing", () => {
    render(<RiskDashboard data={data({ targets_recorded: false })} />);
    expect(screen.getByTestId("risk-targets-used").textContent).toBe(
      "The targets these findings were measured against were not recorded for this register.",
    );
  });
});
