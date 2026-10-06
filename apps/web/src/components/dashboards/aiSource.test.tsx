import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import type { JSX } from "react";
import { describe, expect, it } from "vitest";

import type { AiSource } from "@/lib/aiSource/types";
import type { AttackDashboardData } from "@/lib/dashboards/attack";
import type { CsfDashboardData } from "@/lib/dashboards/csf";
import type { RiskDashboardData } from "@/lib/dashboards/risk";
import type { TechDebtDashboardData } from "@/lib/dashboards/techDebt";
import type { ZtDashboardData } from "@/lib/dashboards/zt";

import { AttackDashboard } from "./attack/AttackDashboard";
import { CsfDashboard } from "./csf/CsfDashboard";
import { RiskDashboard } from "./risk/RiskDashboard";
import { TechDebtDashboard } from "./techDebt/TechDebtDashboard";
import { ZtDashboard } from "./zt/ZtDashboard";

/**
 * #646 on every client dashboard: the API's own sentence saying which mode
 * drafted the figures, in all five states -- live included, so "no warning"
 * never reads as "nobody looked". The sentence is the API's, never reworded
 * here; fixture, mixed and not recorded are announced (role="alert").
 */

const SOURCES: AiSource[] = [
  {
    state: "live",
    sentence: "AI suggestions in this assessment came from a live AI model.",
    live_runs: 1,
    fixture_runs: 0,
  },
  {
    state: "fixture",
    sentence:
      "OFFLINE TEST DATA: every AI suggestion in this assessment came from built-in test data, not a live AI model. Treat AI-drafted values as placeholders, not analysis.",
    live_runs: 0,
    fixture_runs: 1,
  },
  {
    state: "mixed",
    sentence:
      "OFFLINE TEST DATA: 1 of the 3 AI runs on this assessment used built-in test data, not a live AI model. Values they drafted are placeholders, not analysis.",
    live_runs: 2,
    fixture_runs: 1,
  },
  {
    state: "none",
    sentence: "No AI suggestions were used in this assessment.",
    live_runs: 0,
    fixture_runs: 0,
  },
  {
    state: "unknown",
    sentence:
      "It is not recorded whether the AI suggestions in this assessment came from a live AI model or from offline test data.",
    live_runs: 0,
    fixture_runs: 0,
  },
];

const BASE = {
  service_id: "11111111-1111-4111-8111-111111111111",
  service_title: "Assessment",
  released_at: "2026-09-09T00:00:00Z",
  deliverable_version: 1,
};

const DASHBOARDS: [string, (s: AiSource) => JSX.Element][] = [
  [
    "ATT&CK",
    (s) => (
      <AttackDashboard
        data={
          {
            ...BASE,
            ai_source: s,
            rollup: {
              total_evaluated: 0,
              covered: 0,
              partial: 0,
              gap: 0,
              not_applicable: 0,
              coverage_pct: 0,
              by_tactic: [],
            },
            techniques: [],
          } as unknown as AttackDashboardData
        }
      />
    ),
  ],
  [
    "CSF",
    (s) => (
      <CsfDashboard
        data={
          {
            ...BASE,
            ai_source: s,
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
          } as unknown as CsfDashboardData
        }
      />
    ),
  ],
  [
    "Zero Trust",
    (s) => (
      <ZtDashboard
        data={
          {
            ...BASE,
            ai_source: s,
            unusable_target_codes: [],
            framework: "cisa_ztmm_2_0",
            framework_label: "CISA ZTMM 2.0",
            current_label: "Initial",
            current_pct: 40,
            target_label: "Advanced",
            target_pct: 70,
            target_stage: 3,
            target_stage_source: "client",
            target_frozen_at: "2026-09-09T00:00:00Z",
            engagement_target_capability_count: 0,
            total_gap_count: 0,
            largest_gap_pillar: null,
            largest_gap_pct: 0,
            pillars: [],
          } as unknown as ZtDashboardData
        }
      />
    ),
  ],
  [
    "Tech Debt",
    (s) => (
      <TechDebtDashboard
        data={
          {
            ...BASE,
            ai_source: s,
            total_applications: 0,
            annual_spend_usd: 0,
            identified_savings_usd: 0,
            savings_cost_known: true,
            spend_completeness: "complete",
            source_rows_total: 0,
            included_count: 0,
            excluded_count: 0,
            redundant_category_count: 0,
            spend_by_category: [],
            sprawl_by_category: [],
            redundancies: [],
            items: [],
          } as unknown as TechDebtDashboardData
        }
      />
    ),
  ],
  [
    "Risk",
    (s) => (
      <RiskDashboard
        data={
          {
            ai_source: s,
            client_id: "00000000-0000-0000-0000-0000000000aa",
            released_at: "2026-09-20T00:00:00Z",
            version: 3,
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
          } as unknown as RiskDashboardData
        }
      />
    ),
  ],
];

describe.each(DASHBOARDS)("the %s client dashboard (#646)", (_name, view) => {
  it.each(SOURCES.map((s) => [s.state, s] as const))(
    "states the AI source when it is %s",
    (state, source) => {
      render(view(source));
      const note = screen.getByTestId("ai-source");
      expect(note).toHaveTextContent(source.sentence);
      expect(note).toHaveAttribute("data-state", state);
      if (state === "live" || state === "none") {
        expect(note).not.toHaveAttribute("role");
      } else {
        expect(note).toHaveAttribute("role", "alert");
      }
    },
  );
});
