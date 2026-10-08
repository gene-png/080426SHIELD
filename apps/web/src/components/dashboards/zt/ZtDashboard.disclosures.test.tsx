import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ZtDashboardData } from "@/lib/dashboards/zt";

import { ZtDashboard } from "./ZtDashboard";

/**
 * #839, approved at #736 comment 6049667540, texts copied from 6049167247:
 *
 * - S1: a stage stored above its capability's maximum, beside the cap notes;
 * - S2 (#914): answers kept on rows the catalog no longer has, the approved
 *   `retired_sentence` reused verbatim.
 *
 * Both are the API's own sentences, rendered as given. The fixture is shaped
 * like `ZtDashboardResponse`.
 */

const S1 =
  "1.1 User Inventory is recorded at stage 3, but it has no DoD Advanced activities, so every figure here counts it as Target (2).";
const S2 =
  "6 recorded answers belong to rows that the DoD Zero Trust Execution Roadmap does not have, so they are not scored.";

function dashboard(over: Partial<ZtDashboardData>): ZtDashboardData {
  return {
    ai_source: {
      state: "live",
      sentence: "AI suggestions in this assessment came from a live AI model.",
      live_runs: 1,
      fixture_runs: 0,
    },
    service_id: "11111111-1111-4111-8111-111111111111",
    unusable_target_codes: [],
    target_cap_notes: [],
    service_title: "Zero Trust Assessment",
    released_at: "2026-09-09T00:00:00Z",
    deliverable_version: 1,
    framework: "dod_ztra",
    framework_label: "DoD ZTRA",
    current_label: "Target",
    current_pct: 40,
    target_label: "Advanced",
    target_pct: 70,
    target_stage: 3,
    target_stage_source: "client",
    target_frozen_at: "2026-09-09T00:00:00Z",
    engagement_target_capability_count: 4,
    total_gap_count: 1,
    largest_gap_pillar: "User",
    largest_gap_pct: 30,
    pillars: [
      {
        code: "USR",
        name: "User",
        capability_count: 4,
        answered_count: 4,
        current_pct: 40,
        current_label: "Target",
        target_pct: 70,
        target_label: "Advanced",
        gap_pct: 30,
        weakest: [],
      },
    ],
    ...over,
  } as ZtDashboardData;
}

describe("ZtDashboard states a stored stage above its maximum (#839 S1)", () => {
  it("lists the API's sentence", () => {
    render(<ZtDashboard data={dashboard({ stage_above_max_notes: [S1] })} />);
    expect(screen.getByTestId("zt-stage-above-max")).toHaveTextContent(S1);
  });

  it("shows nothing when every stage is reachable", () => {
    render(<ZtDashboard data={dashboard({ stage_above_max_notes: [] })} />);
    expect(screen.getByText("Target maturity")).toBeInTheDocument();
    expect(screen.queryByTestId("zt-stage-above-max")).toBeNull();
  });
});

describe("ZtDashboard states retired answers (#914, S2)", () => {
  it("renders the API's note", () => {
    render(
      <ZtDashboard
        data={dashboard({ retired_answers: 6, retired_answers_note: S2 })}
      />,
    );
    expect(screen.getByTestId("zt-retired-answers")).toHaveTextContent(S2);
  });

  it("shows nothing when there are none", () => {
    render(
      <ZtDashboard
        data={dashboard({ retired_answers: 0, retired_answers_note: null })}
      />,
    );
    expect(screen.getByText("Target maturity")).toBeInTheDocument();
    expect(screen.queryByTestId("zt-retired-answers")).toBeNull();
  });
});
