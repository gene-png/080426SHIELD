import "@testing-library/jest-dom/vitest";

import * as React from "react";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as csfClient from "@/lib/csf/client";
import type { EnterpriseProfile } from "@/lib/csf/types";

import { CsfPlaybookPanel } from "./CsfPlaybookPanel";

/** CSF Options 1 and 3 through the panel, in the text Gene approved (#736
 * 6205956728): a subcategory with no scored tier reads "Not scored" in
 * Enterprise (never "Lnull") with its C1 line, a scored one reads its level's
 * name (C14), its tiers (C12) and its evidence (C8), and the C3 and E3 lines
 * state the API's counts, E3 only where evidence labels a level. Every
 * expected string is typed here, never imported. Harness from
 * CsfPlaybookPanel.unscored.test.tsx. */
vi.mock("@/lib/csf/client", () => ({
  CsfProxyError: class CsfProxyError extends Error {},
  fetchEnterpriseProfile: vi.fn(),
  seedProfiles: vi.fn(),
  runCsfAi: vi.fn(),
  exportPlaybook: vi.fn(),
  fetchCsfRun: vi.fn(),
  fetchCsfRunSummary: vi.fn(),
}));
vi.mock("../AiPreviewButton", () => ({ AiPreviewButton: () => null }));
// Renders what the panel hands it: whether editing is locked.
vi.mock("./CsfDimensionEditor", () => ({
  CsfDimensionEditor: (props: { readOnly?: boolean }) => (
    <div data-testid="editor-read-only">{String(props.readOnly)}</div>
  ),
}));
vi.mock("./CsfGapActionEditor", () => ({ CsfGapActionEditor: () => null }));
// The REAL RunAiGuard (#645): its AI status is what each test sets here, so
// these tests reach the guard's fail-closed path through this surface.
const aiStatus = vi.hoisted(() => {
  const ok = {
    ready: true,
    serves: "live",
    mode: "fixture",
    provider: "anthropic",
    model: "m",
    detail: "",
    can_configure: true,
    key_source: "database",
  };
  return {
    ok,
    current: { status: ok as unknown, phase: "loaded" as string },
    refresh: vi.fn(),
  };
});
vi.mock("@/lib/admin/aiStatus", () => ({
  useAiStatus: () => ({
    status: aiStatus.current.status,
    phase: aiStatus.current.phase,
    settled: async () => aiStatus.current.status,
    refresh: aiStatus.refresh,
  }),
  // An offline status counts as already acknowledged, so a click proceeds.
  hasAcknowledgedOffline: () => true,
  acknowledgeOffline: () => undefined,
}));

const ent = vi.mocked(csfClient.fetchEnterpriseProfile);
const summary = vi.mocked(csfClient.fetchCsfRunSummary);

type Sub = EnterpriseProfile["subcategories"][number];

function row(code: string, over: Partial<Sub>): Sub {
  return {
    subcategory_code: code,
    name: `${code} outcome`,
    function: "GV",
    tier_levels: { high: 3 },
    enterprise_level: 3,
    rollup_rule: 1,
    target_level: null,
    gap: false,
    priority: null,
    no_notes: false,
    tier_evidence: { high: "on_file" },
    ...over,
  };
}

const COVERAGE = {
  total: 9,
  scored: 2,
  notes_not_scored: 1,
  self_reported: 3,
  not_answered: 3,
  evidence_on_file: 0,
  evidence_confirmed: 1,
  evidence_neither: 1,
  evidence_mixed: 0,
  notional: 1,
};

function profile(evidenceCap: boolean): EnterpriseProfile {
  return {
    tiers_in_use: ["high"],
    subcategories: [
      row("GV.OC-01", {}),
      row("GV.OC-02", {
        tier_levels: {},
        enterprise_level: null,
        rollup_rule: null,
        scored: false,
        self_rating: 2,
        no_notes: true,
      }),
    ],
    coverage: COVERAGE,
    evidence_cap: evidenceCap,
  };
}

const C3 =
  "2 of 9 subcategories scored; 1 with notes, not yet scored; 3 self-reported only, not validated; 3 not answered.";
const E3 =
  "Of the 2 scored subcategories: 0 with evidence on file for every scored tier; 1 confirmed in discussion (every scored tier on file or confirmed, at least one confirmed); 0 mixed (at least one scored tier with neither, and at least one with evidence on file or confirmed); 1 with neither on any scored tier; 1 at Managed or Optimized are notional.";

function rowOf(code: string): HTMLElement {
  const tr = screen.getByText(code).closest("tr");
  if (!tr) throw new Error(`no table row for ${code}`);
  return tr;
}

beforeEach(() => {
  vi.clearAllMocks();
  aiStatus.current = { status: aiStatus.ok, phase: "loaded" };
  summary.mockResolvedValue({
    running: null,
    latest: null,
    last_completed: null,
  });
});

describe("CsfPlaybookPanel, Options 1 and 3", () => {
  it("states C3 and E3 when evidence labels the level", async () => {
    ent.mockResolvedValue(profile(false));
    render(<CsfPlaybookPanel serviceId="svc-1" />);
    expect(await screen.findByTestId("csf-coverage")).toHaveTextContent(C3);
    expect(screen.getByTestId("csf-evidence-coverage")).toHaveTextContent(E3);
  });

  it("states neither line on a frozen assessment, whose unscored rows keep their levels", async () => {
    // #1203 review: on rules 1 or 2 an unscored subcategory keeps the level
    // it was delivered with, so a "not scored" count would contradict the
    // table, and under the cap "notional" describes nothing.
    ent.mockResolvedValue(profile(true));
    render(<CsfPlaybookPanel serviceId="svc-1" />);
    expect(await screen.findByText("GV.OC-01")).toBeInTheDocument(); // positive first
    expect(screen.queryByTestId("csf-coverage")).toBeNull();
    expect(screen.queryByTestId("csf-evidence-coverage")).toBeNull();
  });

  it("reads Not scored in Enterprise for a subcategory with no level", async () => {
    ent.mockResolvedValue(profile(false));
    render(<CsfPlaybookPanel serviceId="svc-1" />);
    await screen.findByText("GV.OC-02");
    const scored = rowOf("GV.OC-01"); // positive first
    expect(scored).toHaveTextContent("Defined");
    expect(scored).toHaveTextContent("Evidence on file (High)");
    const cells = Array.from(rowOf("GV.OC-02").querySelectorAll("td")).map(
      (td) => td.textContent,
    );
    expect(cells).toContain("Not scored");
    expect(rowOf("GV.OC-02")).toHaveTextContent(
      "Self-reported, not validated: Tier 2 (Risk Informed). No notes, so not scored.",
    );
    expect(cells.join(" ")).not.toMatch(/Lnull|L0\b|#null/);
  });
});
