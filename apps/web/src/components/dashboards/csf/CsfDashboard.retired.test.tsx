import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { CsfDashboardData } from "@/lib/dashboards/csf";

import { CsfDashboard } from "./CsfDashboard";

/**
 * #852: an answer kept on ID.AM-09 (a subcategory NIST CSF 2.0 does not have)
 * is in no figure on this dashboard, and the API sends the approved sentence
 * saying so. The client reads it here or nowhere. Rendered as given.
 */

const S1 =
  "1 recorded answer belongs to ID.AM-09, a subcategory NIST CSF 2.0 does not" +
  " have, so it is not scored.";

function dashboard(over: Partial<CsfDashboardData>): CsfDashboardData {
  return {
    ai_source: {
      state: "live",
      sentence: "AI suggestions in this assessment came from a live AI model.",
      live_runs: 1,
      fixture_runs: 0,
    },
    service_id: "11111111-1111-4111-8111-111111111111",
    service_title: "NIST CSF 2.0 Assessment",
    released_at: "2026-09-09T00:00:00Z",
    deliverable_version: 1,
    overall_label: "Risk Informed",
    current_tier: 2,
    current_pct: 50,
    coverage_pct: 100,
    target_tier: 3,
    target_label: "Repeatable",
    target_pct: 75,
    target_tier_source: "client",
    target_frozen_at: "2026-09-09T00:00:00Z",
    total_gap_count: 0,
    largest_gap_function: null,
    largest_gap_pct: 0,
    functions: [],
    top_gaps: [],
    ...over,
  } as CsfDashboardData;
}

describe("CsfDashboard states an answer kept on a retired subcategory (#852)", () => {
  it("renders the API's sentence", () => {
    render(
      <CsfDashboard
        data={dashboard({ retired_answers: 1, retired_answers_note: S1 })}
      />,
    );
    expect(screen.getByTestId("csf-retired-answers")).toHaveTextContent(S1);
  });

  it("says nothing when nothing was kept", () => {
    render(
      <CsfDashboard
        data={dashboard({ retired_answers: 0, retired_answers_note: null })}
      />,
    );
    expect(screen.getByText("Your target, chosen at intake.")).toBeVisible();
    expect(screen.queryByTestId("csf-retired-answers")).toBeNull();
  });
});
