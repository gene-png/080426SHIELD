import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ZtDashboardData } from "@/lib/dashboards/zt";

import { ZtDashboard } from "./ZtDashboard";

/**
 * #208 at the WIRING SEAM, which `stageAxis.test.ts` does not reach.
 *
 * Independent verification of `5f96960` found the gap and proved it rather
 * than argued it: restoring `ZtDashboard.tsx` to its pre-fix content — the
 * hardcoded CISA axis — while KEEPING `stageAxis.ts` and its five tests left
 * the whole suite green, 317/317, tsc 0. The revert was proved to have landed
 * first (`grep -c "Optimal</span>"` -> 1, `grep -c "stageAxis"` -> 0).
 *
 * So the literal defect in #208 was reintroducible with every gate passing.
 * The unit tests discriminate for the MODULE — a `stageAxis` returning CISA
 * labels everywhere fails them — but nothing asserted that the component
 * passes `data.framework` or renders what comes back. That is #72's shape
 * moved to the seam between a correct function and its caller.
 *
 * These tests render the component. They fail on exactly that revert.
 */

const dodPillar = {
  code: "device",
  name: "Device",
  capability_count: 4,
  answered_count: 4,
  current_pct: 40,
  current_label: "Target",
  target_pct: 70,
  target_label: "Advanced",
  gap_pct: 30,
  weakest: [],
};

function dashboard(
  framework: string,
  unusable: string[] = [],
): ZtDashboardData {
  return {
    service_id: "11111111-1111-4111-8111-111111111111",
    unusable_target_codes: unusable,
    service_title: "Zero Trust Assessment",
    released_at: "2026-09-09T00:00:00Z",
    deliverable_version: 1,
    framework,
    framework_label: framework === "dod_ztra" ? "DoD ZTRA" : "CISA ZTMM 2.0",
    current_label: "Target",
    current_pct: 40,
    target_label: "Advanced",
    target_pct: 70,
    target_stage: 2,
    // "client", not "engagement". `resolve_target_stage` returns exactly four
    // values -- "client", "default", "client_out_of_range",
    // "client_unparseable" -- so the previous fixture built a state no writer
    // can produce, and `targetNote` rendered it through its unrecognised-value
    // fallback ("Default target -- the stage on file was not usable"). Inert
    // for the legend tests below, which read the axis and not the note; the
    // disclosure tests read the note, so they need a reachable state.
    target_stage_source: "client",
    engagement_target_capability_count: 4,
    total_gap_count: 1,
    largest_gap_pillar: "Device",
    largest_gap_pct: 30,
    pillars: [dodPillar],
  };
}

describe("ZtDashboard maturity legend (wiring)", () => {
  it("never shows a CISA stage name to a DoD engagement", () => {
    render(<ZtDashboard data={dashboard("dod_ztra")} />);
    // "Optimal" is the one that cannot be explained away as shared wording:
    // it is not a DoD stage at all, and it is the label #125 removed from the
    // intake UI for the same reason.
    expect(screen.queryByText("Optimal")).not.toBeInTheDocument();
    expect(screen.queryByText("Initial")).not.toBeInTheDocument();
  });

  it("shows the DoD ladder to a DoD engagement", () => {
    render(<ZtDashboard data={dashboard("dod_ztra")} />);
    expect(screen.getByText("Not Started")).toBeInTheDocument();
    expect(screen.getByText("Target")).toBeInTheDocument();
  });

  it("still shows the CISA ladder to a CISA engagement", () => {
    // The fix must not have traded one wrong axis for another: a component
    // that rendered DoD's labels everywhere would pass the first two tests.
    render(<ZtDashboard data={dashboard("cisa_ztmm_2_0")} />);
    expect(screen.getByText("Optimal")).toBeInTheDocument();
    expect(screen.getByText("Traditional")).toBeInTheDocument();
  });

  it("renders NO legend for a framework it does not recognise", () => {
    // Absent beats wrong. The bars stay correct because the server normalised
    // them; a missing legend is visible to a reader and a wrong one is not.
    render(<ZtDashboard data={dashboard("some_future_framework")} />);
    for (const label of [
      "Traditional",
      "Initial",
      "Advanced",
      "Optimal",
      "Not Started",
      "Target",
    ]) {
      expect(screen.queryByText(label)).not.toBeInTheDocument();
    }
  });
});

describe("ZtDashboard discarded-target disclosure (wiring)", () => {
  /**
   * #387 at the SAME SEAM, and added because the fix shipped without it.
   *
   * `targetNote` is a pure function with three tests of its own. `CLAUDE.md`
   * is explicit that a pure function is not the surface a client reaches:
   * delete `sub={targetNote(data)}` from `ZtDashboard.tsx`, or pass it a
   * different object, and every one of those three stays green while the
   * client sees nothing. That is the defect the legend tests above were
   * written for, one card over.
   */
  const SENTENCE = /A per-capability target was recorded for/;

  it("prints the discarded capabilities on the rendered card", () => {
    render(
      <ZtDashboard
        data={dashboard("cisa_ztmm_2_0", ["CISA.ID.01", "CISA.ID.02"])}
      />,
    );
    // The codes themselves, not just the lead-in: a sentence that named the
    // fault and dropped the rows would satisfy a looser assertion and tell
    // the client nothing actionable.
    expect(screen.getByText(SENTENCE)).toHaveTextContent(
      "CISA.ID.01, CISA.ID.02",
    );
  });

  it("says nothing on a card with no discarded targets", () => {
    // The negative control. Without it, a component that printed the sentence
    // unconditionally would pass the case above.
    render(<ZtDashboard data={dashboard("cisa_ztmm_2_0")} />);
    // Assert what must APPEAR before what must not. A `queryByText` returning
    // null is also what a card that threw, or never mounted, looks like --
    // so pin the note that DOES belong on this card first, and only then the
    // absence. Without this line the case passes over a dead render.
    expect(screen.getByText("Your target, chosen at intake")).toBeVisible();
    expect(screen.queryByText(SENTENCE)).not.toBeInTheDocument();
  });

  it("prints it under a DoD engagement too", () => {
    // The disclosure is about rows, not about which ladder the engagement
    // uses, so it must not ride on the framework branch.
    render(<ZtDashboard data={dashboard("dod_ztra", ["DOD.DEV.02"])} />);
    expect(screen.getByText(SENTENCE)).toHaveTextContent("DOD.DEV.02");
  });
});
