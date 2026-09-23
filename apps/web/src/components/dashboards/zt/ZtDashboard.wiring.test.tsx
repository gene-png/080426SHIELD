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
  source = "client",
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
    target_stage_source: source,
    // #209: frozen, which is what every deliverable this product builds
    // carries. Inert for the legend tests; the disclosure lives in
    // `zt.test.ts`, which exercises both states of it directly.
    target_frozen_at: "2026-09-09T00:00:00Z",
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
   * `targetNote` is a pure function with tests of its own. `CLAUDE.md` is
   * explicit that a pure function is not the surface a client reaches:
   * replace `sub={targetNote(data)}` in `ZtDashboard.tsx` with a constant and
   * every one of those stays green while the card prints a sentence the
   * assessment does not support. That is the defect the legend tests above
   * were written for, one card over.
   *
   * DELETING the prop is NOT that defect, and an earlier draft of this
   * docstring said it was. `KpiCard`'s props are
   * `{ label, value, sub, accent? }` with `sub` REQUIRED, so a deletion is a
   * tsc error and the loop gate catches it loudly. Only the SUBSTITUTION is
   * silent -- which matters, because a reader told the type system gives no
   * protection here would go looking for the wrong class of mutant.
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
    // Assert what must APPEAR before what must not -- but for a NARROWER
    // reason than the repo rule gives, and the narrow one is the true one.
    //
    // A card that THREW does not need this line: there is no error boundary
    // around `render()`, so React re-throws and the test fails either way.
    // The repo rule's original case is an async page asserting absence
    // mid-fetch, and `render()` here is synchronous, so that cannot happen
    // either. What this line uniquely catches is the render that SUCCEEDS and
    // produces nothing to read -- `sub={""}`, `targetNote` returning empty,
    // the KpiCard or the whole KpiRow removed. That class is real and nothing
    // else here covers it.
    //
    // `toBeVisible` over `toBeInTheDocument` because it also catches
    // `display: none`. In jsdom it is a style check and not a layout one, so
    // it is NOT evidence about clipping; that was settled by reading
    // `KpiCard`'s styles instead.
    expect(screen.getByText("Your target, chosen at intake")).toBeVisible();
    expect(screen.queryByText(SENTENCE)).not.toBeInTheDocument();
  });

  it("renders the FAULT wording at the seam, not just the no-fault one", () => {
    // The gap the review found in the first draft: every case above renders
    // the no-fault card, so nothing exercised the sentence a consultant acts
    // on. #125 went to trouble to keep "the client chose nothing" apart from
    // "the client's choice could not be used" -- only the second is
    // answerable by re-asking -- and that distinction had never been rendered
    // by any test, only returned by a pure function.
    //
    // `client_out_of_range` rather than `default`, because it is the arm that
    // carries the actionable fact.
    render(
      <ZtDashboard
        data={dashboard("dod_ztra", ["DOD.DEV.02"], "client_out_of_range")}
      />,
    );
    expect(
      screen.getByText(
        /Default target . the stage on file is not one this framework has/,
      ),
    ).toBeVisible();
    // And the disclosure rides alongside it rather than replacing it -- the
    // two facts are independent, which is the whole design of `targetNote`.
    expect(screen.getByText(SENTENCE)).toHaveTextContent("DOD.DEV.02");
  });

  it("prints it under a DoD engagement too", () => {
    // The disclosure is about rows, not about which ladder the engagement
    // uses, so it must not ride on the framework branch.
    render(<ZtDashboard data={dashboard("dod_ztra", ["DOD.DEV.02"])} />);
    expect(screen.getByText(SENTENCE)).toHaveTextContent("DOD.DEV.02");
  });
});
