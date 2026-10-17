import "@testing-library/jest-dom/vitest";

import * as React from "react";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as csfClient from "@/lib/csf/client";
import type { EnterpriseProfile } from "@/lib/csf/types";

import { CsfPlaybookPanel } from "./CsfPlaybookPanel";

/** #1031 through the CSF panel (#736 6127667643, copy approved verbatim): an
 * unscored in-scope tier reads "Not scored" and is never dropped, and a
 * subcategory whose only targets sit on unscored tiers reads "Not measured"
 * in Target and Gap. Harness from CsfPlaybookPanel.no-notes.test.tsx. */
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

function row(
  code: string,
  over: Partial<EnterpriseProfile["subcategories"][number]>,
): EnterpriseProfile["subcategories"][number] {
  return {
    subcategory_code: code,
    name: `${code} outcome`,
    function: "GV",
    tier_levels: {},
    enterprise_level: 3,
    rollup_rule: 1,
    target_level: null,
    gap: false,
    priority: null,
    no_notes: false,
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  aiStatus.current = { status: aiStatus.ok, phase: "loaded" };
  summary.mockResolvedValue({
    running: null,
    latest: null,
    last_completed: null,
  });
  ent.mockResolvedValue({
    tiers_in_use: ["high", "moderate", "low"],
    subcategories: [
      row("GV.OC-01", {
        tier_levels: { high: 3 },
        unscored_tiers: ["moderate", "low"],
        target_level: 3,
      }),
      row("GV.OC-02", {
        tier_levels: { high: 3 },
        unscored_tiers: ["moderate"],
        target_not_measured: true,
      }),
      row("GV.OC-03", { tier_levels: { high: 2, moderate: 1 } }),
      row("GV.OC-04", { tier_levels: { high: 3 } }),
    ],
  });
});

function rowOf(code: string): HTMLElement {
  const cell = screen.getByText(code);
  const tr = cell.closest("tr");
  if (!tr) throw new Error(`no table row for ${code}`);
  return tr;
}

describe("CsfPlaybookPanel, unscored tiers and unmeasured targets (#1031)", () => {
  it("names every unscored in-scope tier rather than dropping it", async () => {
    render(<CsfPlaybookPanel serviceId="svc-1" />);
    expect(
      // C12 (#736 6205956728): level names grouped by tier.
      await screen.findByText(
        "Defined (High) \u00b7 Not scored (Moderate, Low)",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Developing (High) \u00b7 Ad hoc (Moderate)"),
    ).toBeInTheDocument();
  });

  it("reads Not measured in Target and Gap when the only target is unscored", async () => {
    render(<CsfPlaybookPanel serviceId="svc-1" />);
    await screen.findByText("GV.OC-02");
    const measured = rowOf("GV.OC-02");
    expect(measured).toHaveTextContent("Not measured");
    expect(
      Array.from(measured.querySelectorAll("td")).filter(
        (td) => td.textContent === "Not measured",
      ),
    ).toHaveLength(2);
    // A row with no target at all keeps its dash, never "Not measured".
    expect(rowOf("GV.OC-04")).not.toHaveTextContent("Not measured");
  });

  it("counts an unmeasured target apart from no target (review F2)", async () => {
    render(<CsfPlaybookPanel serviceId="svc-1" />);
    const line = await screen.findByText(/tier\(s\) in use/);
    expect((line.textContent ?? "").replace(/\s+/g, " ").trim()).toBe(
      "3 tier(s) in use · 0 subcategories with a gap · 2 with no target · 1 not measured",
    );
  });
});
