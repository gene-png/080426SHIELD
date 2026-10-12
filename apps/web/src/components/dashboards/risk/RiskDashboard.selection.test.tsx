import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RiskDashboard } from "./RiskDashboard";
import type { RiskDashboardData } from "@/lib/dashboards/risk";

/**
 * RR-1 (for #1122), design note §6.1 and §6.2: the client's dashboard says
 * what the register was generated from and what was left out (copy 8,
 * 9a-9c), or copy 11 when it has no usable record of that, directly before
 * the target lines; and it renders each target row's `label` as the server
 * gives it. Expected strings are §8's, verbatim.
 */
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

const COPY_11 =
  "This register has no usable record of how its services were chosen or which were left out.";

function lines(): string[] {
  return Array.from(
    screen.getByTestId("risk-selection-lines").querySelectorAll("p"),
  ).map((p) => p.textContent ?? "");
}

describe("RiskDashboard, what the register was generated from (RR-1)", () => {
  it.each([
    ["absent", {}],
    [
      "false",
      { selection_recorded: false, covered_inputs: ["ATT&CK coverage"] },
    ],
  ])("prints copy 11 alone when selection_recorded is %s", (_n, over) => {
    render(<RiskDashboard data={data(over)} />);
    expect(lines()).toEqual([COPY_11]);
  });

  it("prints copy 8 for a register that left nothing out", () => {
    render(
      <RiskDashboard
        data={data({
          selection_recorded: true,
          covered_inputs: ["ATT&CK coverage", "NIST CSF"],
          deselected_inputs: [],
          ineligible_inputs: [],
        })}
      />,
    );
    expect(lines()).toEqual([
      "This register was generated from ATT&CK coverage and NIST CSF.",
    ]);
  });

  it("prints copy 8, 9a and 9c, in that order", () => {
    render(
      <RiskDashboard
        data={data({
          selection_recorded: true,
          covered_inputs: ["ATT&CK coverage", "NIST CSF"],
          deselected_inputs: ["Zero Trust (CISA ZTMM 2.0)"],
          ineligible_inputs: ["Zero Trust (DoD ZT Reference Architecture)"],
        })}
      />,
    );
    expect(lines()).toEqual([
      "This register was generated from ATT&CK coverage and NIST CSF.",
      "Zero Trust (CISA ZTMM 2.0) was not included in this register.",
      "Zero Trust (DoD ZT Reference Architecture) was engaged but had no assessment when this register was generated, so it is not in this register.",
    ]);
  });

  it("prints the lines before the target lines", () => {
    render(<RiskDashboard data={data({ selection_recorded: false })} />);
    const sel = screen.getByTestId("risk-selection-lines");
    const targets = screen.getByTestId("risk-targets-used");
    expect(
      sel.compareDocumentPosition(targets) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("names the framework on the A8 register's one ZT target row, from its label", () => {
    // A8: CISA eligible, DoD engaged with no assessment. One ZT row, which
    // the server names because the register mentions two Zero Trust services.
    render(
      <RiskDashboard
        data={data({
          selection_recorded: true,
          covered_inputs: ["ATT&CK coverage", "Zero Trust (CISA ZTMM 2.0)"],
          ineligible_inputs: ["Zero Trust (DoD ZT Reference Architecture)"],
          targets: [
            {
              kind: "zt",
              framework: "cisa_ztmm_2_0",
              target: 4,
              source: "client",
              origin: "live_at_generate",
              label: "Zero Trust (CISA ZTMM 2.0)",
            },
          ],
          targets_recorded: true,
        })}
      />,
    );
    expect(screen.getByTestId("risk-targets-used").textContent).toBe(
      "Zero Trust (CISA ZTMM 2.0) findings are measured against target stage 4, the engagement target when this register was generated.",
    );
  });
});
