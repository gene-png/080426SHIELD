import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RiskDashboard } from "./RiskDashboard";
import type { RiskDashboardData } from "@/lib/dashboards/risk";

// ---------------------------------------------------------------------------
// #313 -- the qualifier is computed, published to the ADMIN, and withheld from
// the CLIENT.
//
// `routes/clients.py::risk_dashboard` publishes `total_entries=len(entries)`
// while `tier_counts`, `axis_counts`, `action_counts` and `matrix` are all
// computed over SILENTLY FILTERED lists: `[t for t in (...) if t is not None]`.
// So an entry with no tier is counted in the headline and dropped from every
// breakdown, and the two disagree with nothing explaining the gap.
//
// This is already disclosed -- on the admin surface ONLY. `_serialize`
// publishes `entries_without_tier`, `RiskRegisterDashboard.tsx` renders a
// role="alert" banner for it, and that banner's own copy ends by saying a
// client reading this register sees those rows as dashes. The admin is told
// the client sees the undisclosed version, and the client surface was left in
// exactly that state.
//
// RENDER-SIDE AND WRITTEN FIRST, per the definition-of-done rule: a field that
// records what was withheld is finished when a person can see it, and the
// endpoint is not the surface.
// ---------------------------------------------------------------------------

function data(overrides: Partial<RiskDashboardData> = {}): RiskDashboardData {
  return {
    client_id: "00000000-0000-0000-0000-0000000000aa",
    released_at: "2026-09-20T00:00:00Z",
    version: 3,
    total_entries: 40,
    critical_count: 4,
    high_count: 9,
    tier_counts: { critical: 4, high: 9, medium: 10, low: 5 },
    axis_counts: { confidentiality: 12, integrity: 10, availability: 6 },
    action_counts: { mitigate: 20, accept: 8 },
    matrix: [],
    entries: [],
    ...overrides,
  } as RiskDashboardData;
}

describe("RiskDashboard withheld-entry disclosure (#313)", () => {
  it("says so when entries are counted in the headline but missing from the breakdowns", () => {
    render(
      <RiskDashboard
        data={data({ total_entries: 40, entries_without_tier: 12 })}
      />,
    );

    const note = screen.getByTestId("risk-entries-without-tier");
    expect(note).toBeInTheDocument();
    // BOTH operands, because the point is the DISAGREEMENT between them. A
    // bare "12 entries incomplete" does not tell a reader why the tiers sum
    // to 28 under a headline of 40.
    expect(note).toHaveTextContent(/12/);
    expect(note).toHaveTextContent(/40/);
  });

  it("is an alert, not a footnote", () => {
    // The client is reading a published register. A qualifier on a figure they
    // are about to act on has to be announced, not discoverable -- the admin
    // surface already uses role="alert" for the same fact.
    render(
      <RiskDashboard
        data={data({ total_entries: 40, entries_without_tier: 12 })}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(/12/);
  });

  it("does not stay silent when the gap is in the AXIS breakdown", () => {
    // THE FALSE ALL-CLEAR. The first version derived ONE count, from the tier
    // filter, and claimed the entries were missing from "every breakdown".
    // `tiers`, `axes` and `actions` filter INDEPENDENTLY, and `_coerce_enum`
    // returns `(None, raw)` for any value `RiskAxis` does not have -- so a
    // model answering "mitigation" produces an entry with a VALID tier and no
    // axis.
    //
    // That entry left `entries_without_tier` at 0, so the banner stayed silent
    // while `axis_counts` summed to fewer than the headline: the original #313
    // defect, under a disclosure certifying it did not exist. Silence as a
    // false all-clear is the more expensive direction.
    render(
      <RiskDashboard
        data={data({
          total_entries: 10,
          entries_without_tier: 0,
          entries_without_axis: 1,
          entries_without_action: 0,
        })}
      />,
    );

    const note = screen.getByTestId("risk-entries-without-tier");
    expect(note).toHaveTextContent("1 are absent from the axis breakdown");
    // And it must NOT claim the tier counts are affected, because they are not.
    expect(note).not.toHaveTextContent("absent from the 5x5 matrix");
  });

  it("names every affected breakdown, not just the first", () => {
    render(
      <RiskDashboard
        data={data({
          total_entries: 10,
          entries_without_tier: 2,
          entries_without_axis: 1,
          entries_without_action: 3,
        })}
      />,
    );
    const note = screen.getByTestId("risk-entries-without-tier");
    expect(note).toHaveTextContent(
      "2 are absent from the 5x5 matrix and the tier counts",
    );
    expect(note).toHaveTextContent("1 are absent from the axis breakdown");
    expect(note).toHaveTextContent("3 are absent from the action breakdown");
  });

  it("stays silent when every entry is accounted for", () => {
    // THE OTHER HALF. A banner that always renders is not a disclosure, it is
    // furniture, and a reader learns to skip it -- which is worse than no
    // banner, because the one time it matters it looks the same.
    render(
      <RiskDashboard
        data={data({ total_entries: 40, entries_without_tier: 0 })}
      />,
    );
    expect(
      screen.queryByTestId("risk-entries-without-tier"),
    ).not.toBeInTheDocument();
  });

  it("treats a MISSING count as not-recorded rather than as zero", () => {
    // A register serialized before this field existed carries no count. That
    // is "nobody looked", not "nothing was withheld", and rendering silence
    // for it would be a positive certificate manufactured out of absence --
    // the exact shape #244 was filed for.
    const older = data({ total_entries: 40 });
    delete (older as Partial<RiskDashboardData>).entries_without_tier;
    render(<RiskDashboard data={older} />);

    const note = screen.getByTestId("risk-entries-without-tier");
    expect(note).toHaveTextContent(/not recorded/i);
  });
});
