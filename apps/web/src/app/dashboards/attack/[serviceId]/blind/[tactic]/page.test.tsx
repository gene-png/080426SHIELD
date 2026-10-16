/**
 * #1180 review F1 and F5: the category page answers 404 for a URL segment that
 * names no tactic of the dashboard (a typo, or a tactic the catalog has since
 * renamed) and for one that is not valid percent-encoding, never "No uncovered
 * techniques in this category.". Tested through the PAGE, because the defect
 * was what the page does with the URL.
 */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/lib/api";
import type {
  AttackDashboardData,
  DashTactic,
  DashTechnique,
} from "@/lib/dashboards/attack";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, apiFetch: vi.fn() };
});
vi.mock("@/lib/auth/options", () => ({
  auth: async () => ({ accessToken: "token" }),
}));
vi.mock("@/lib/dashboards/resolveClient", () => ({
  resolveDashboardClientId: async () => "client-1",
}));
const NOT_FOUND = vi.hoisted(() => new Error("not found (test sentinel)"));
vi.mock("next/navigation", () => ({
  redirect: vi.fn(),
  notFound: () => {
    throw NOT_FOUND;
  },
}));
vi.mock("@/components/dashboards/attack/AttackBlindCategory", () => ({
  AttackBlindCategory: ({ slug }: { slug: string }) => (
    <div data-testid="category">{slug}</div>
  ),
}));

import AttackBlindCategoryPage from "./page";

const apiFetch = vi.mocked(api.apiFetch);

function tactic(name: string): DashTactic {
  return {
    tactic_id: name,
    tactic_name: name,
    covered: 0,
    partial: 0,
    gap: 0,
    not_applicable: 0,
    unscored: 0,
    outside_control_surface: 0,
    unable_to_determine: 0,
    coverage_pct: 0,
    coverage_measured: false,
  };
}

const GAP: DashTechnique = {
  code: "T1059",
  name: "Command Interpreter",
  tactic_name: "Execution",
  status: "gap",
  detection_tools: [],
  prevention_tools: [],
  response_tools: [],
  rationale: null,
  computed_parent: false,
  sub_technique_count: 0,
};

const DATA = {
  ai_source: {
    state: "live",
    sentence: "AI suggestions in this assessment came from a live AI model.",
    live_runs: 1,
    fixture_runs: 0,
  },
  service_id: "svc-1",
  service_title: "ATT&CK",
  released_at: "2026-05-12T00:00:00Z",
  deliverable_version: 1,
  rollup: {
    total_evaluated: 1,
    covered: 0,
    partial: 0,
    gap: 1,
    not_applicable: 0,
    outside_control_surface: 0,
    unable_to_determine: 0,
    coverage_pct: 0,
    coverage_measured: true,
    by_tactic: [tactic("Execution"), tactic("Stealth")],
  },
  techniques: [GAP],
} as AttackDashboardData;

function page(segment: string) {
  return AttackBlindCategoryPage({
    params: Promise.resolve({ serviceId: "svc-1", tactic: segment }),
  });
}

beforeEach(() => {
  apiFetch.mockResolvedValue(DATA);
});

describe("ATT&CK blind-spot category page (#1180)", () => {
  it("renders a tactic with blind spots", async () => {
    render(await page("execution"));
    expect(screen.getByTestId("category")).toHaveTextContent("execution");
  });

  it("renders a tactic of the dashboard with nothing uncovered (B-4's case)", async () => {
    render(await page("stealth"));
    expect(screen.getByTestId("category")).toHaveTextContent("stealth");
  });

  it("answers 404 for a segment that names no tactic", async () => {
    await expect(page("defense-evasion")).rejects.toBe(NOT_FOUND);
  });

  it("answers 404 for a segment that is not valid percent-encoding", async () => {
    await expect(page("%E0")).rejects.toBe(NOT_FOUND);
  });
});
