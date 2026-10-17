import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ZtDashboardData } from "@/lib/dashboards/zt";

import { ZtDashboard } from "./ZtDashboard";

/**
 * #1343: the client's ZT dashboard names each applied per-capability target
 * whose origin is not recorded, one line per code under the pillar section,
 * `{code}: <sentence>` (placement approved at #736 6225462107). The sentence
 * is the approved one (6220094031 item 5), quoted here, never imported.
 */

const SENTENCE =
  "Who set this target is not recorded. An earlier AI run may have set it.";

function dashboard(codes: string[] | undefined): ZtDashboardData {
  return {
    ai_source: {
      state: "live",
      sentence: "AI suggestions in this assessment came from a live AI model.",
      live_runs: 1,
      fixture_runs: 0,
    },
    service_id: "11111111-1111-4111-8111-111111111111",
    unusable_target_codes: [],
    unrecorded_target_codes: codes,
    service_title: "Zero Trust Assessment",
    released_at: "2026-09-09T00:00:00Z",
    deliverable_version: 1,
    framework: "cisa_ztmm_2_0",
    framework_label: "CISA ZTMM 2.0",
    current_label: "Initial",
    current_pct: 50,
    target_label: "Advanced",
    target_pct: 75,
    target_stage: 3,
    target_stage_source: "client",
    target_frozen_at: "2026-09-09T00:00:00Z",
    engagement_target_capability_count: 4,
    total_gap_count: 1,
    largest_gap_pillar: "Identity",
    largest_gap_pct: 25,
    pillars: [
      {
        code: "ID",
        name: "Identity",
        capability_count: 4,
        answered_count: 4,
        current_pct: 50,
        current_label: "Initial",
        target_pct: 75,
        target_label: "Advanced",
        gap_pct: 25,
        weakest: [],
      },
    ],
  } as ZtDashboardData;
}

describe("ZtDashboard #1343: targets whose origin is not recorded", () => {
  it("names each code with the approved sentence", () => {
    render(<ZtDashboard data={dashboard(["CISA.ID.01", "CISA.ID.02"])} />);
    expect(screen.getByText(`CISA.ID.01: ${SENTENCE}`)).toBeInTheDocument();
    expect(screen.getByText(`CISA.ID.02: ${SENTENCE}`)).toBeInTheDocument();
  });

  it("says nothing when every applied target's origin is recorded", () => {
    render(<ZtDashboard data={dashboard([])} />);
    expect(screen.getAllByText("Identity").length).toBeGreaterThan(0);
    expect(screen.queryByText(new RegExp(SENTENCE.slice(0, 30)))).toBeNull();
  });

  it("says nothing when the field is absent (an older response)", () => {
    render(<ZtDashboard data={dashboard(undefined)} />);
    expect(screen.getAllByText("Identity").length).toBeGreaterThan(0);
    expect(screen.queryByText(new RegExp(SENTENCE.slice(0, 30)))).toBeNull();
  });
});
