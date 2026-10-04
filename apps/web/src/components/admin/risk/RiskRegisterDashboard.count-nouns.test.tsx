import "@testing-library/jest-dom/vitest";

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as riskClient from "@/lib/risk/client";
import type { RiskEntry, RiskGate, RiskRegister } from "@/lib/risk/types";

import { RiskRegisterDashboard } from "./RiskRegisterDashboard";

/**
 * #743: every count on the admin Risk screen agrees with its noun and verb.
 * Swept by shape (a count beside a noun, and a verb agreeing with the
 * count), so each banner is pinned at 1 with a literal, beside the plural.
 */

vi.mock("@/lib/risk/client", () => ({
  describeRiskError: (e: unknown) => String(e),
  editRiskEntryRating: vi.fn(),
  exportRiskRegister: vi.fn(),
  fetchRiskGate: vi.fn(),
  fetchRiskRegisterLatest: vi.fn(),
  generateRiskRegister: vi.fn(),
  getActiveClientId: vi.fn(),
  getClientName: vi.fn(),
}));

vi.mock("@/components/admin/RunAiGuard", () => ({
  RunAiGuard: ({
    children,
    onProceed,
  }: {
    children: (p: { onClick: () => void }) => React.ReactNode;
    onProceed: () => void;
  }) => children({ onClick: onProceed }),
}));

const fetchRiskGate = vi.mocked(riskClient.fetchRiskGate);
const fetchRiskRegisterLatest = vi.mocked(riskClient.fetchRiskRegisterLatest);
const getActiveClientId = vi.mocked(riskClient.getActiveClientId);
const getClientName = vi.mocked(riskClient.getClientName);

function gate(): RiskGate {
  return {
    unlocked: true,
    has_attack: true,
    has_csf: true,
    has_zt: true,
    missing: [],
    not_finalized: [],
    synthesizable_missing: [],
    attack_catalog_mismatch: null,
  };
}

function entry(over: Partial<RiskEntry> = {}): RiskEntry {
  return {
    id: "e1",
    title: "Credential theft",
    description: null,
    axis: "detection",
    source: "coverage_finding",
    source_id: "T1078",
    linked_techniques: [],
    linked_controls: [],
    likelihood: null,
    impact: null,
    tier: null,
    compensating_controls: null,
    residual_risk: null,
    recommended_action: "remediate",
    rationale: null,
    origin: "ai_generated",
    trust: "admin_assisted",
    dropped_links: {},
    rating_edited_by: null,
    rating_edited_at: null,
    ...over,
  };
}

function register(over: Partial<RiskRegister> = {}): RiskRegister {
  return {
    batches_total: null,
    batches_failed: null,
    entries_intended: null,
    excluded_inputs: [],
    excluded_inputs_recorded: true,
    entries_total: 1,
    entries_without_tier: 1,
    entries_with_dropped_links: 0,
    entries_unlinked_after_drops: 0,
    entries_links_not_recorded: 0,
    excluded_unscored_links: [],
    excluded_unscored_links_recorded: false,
    dropped_citations: null,
    findings_recorded: false,
    findings_total: null,
    findings_without_entry: [],
    findings_with_several_entries: {},
    id: "r1",
    client_id: "c1",
    version: 1,
    generated_by: null,
    finalized_at: null,
    created_at: "2026-10-04T00:00:00Z",
    xlsx_artifact_id: null,
    pdf_artifact_id: null,
    docx_artifact_id: null,
    xlsx_filename: null,
    pdf_filename: null,
    docx_filename: null,
    entries: [entry()],
    tier_counts: {},
    axis_counts: {},
    action_counts: {},
    ...over,
  };
}

async function loaded(): Promise<void> {
  render(<RiskRegisterDashboard />);
  await waitFor(() =>
    expect(
      screen.getByRole("heading", { name: "Risk Register" }),
    ).toBeInTheDocument(),
  );
}

describe("RiskRegisterDashboard count nouns (#743)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getActiveClientId.mockResolvedValue("c1");
    getClientName.mockResolvedValue("Client");
    fetchRiskGate.mockResolvedValue(gate());
  });

  async function textOf(testId: string, over: Partial<RiskRegister>) {
    fetchRiskRegisterLatest.mockResolvedValue(register(over));
    await loaded();
    return (await screen.findByTestId(testId)).textContent ?? "";
  }

  it("one unrated entry of one", async () => {
    const t = await textOf("risk-entries-without-tier", {
      entries_total: 1,
      entries_without_tier: 1,
    });
    expect(t).toContain("1 of 1 entry has no likelihood, impact or tier");
    expect(t).toContain("so it is missing from the matrix");
  });

  it("two unrated entries of three", async () => {
    const t = await textOf("risk-entries-without-tier", {
      entries_total: 3,
      entries_without_tier: 2,
    });
    expect(t).toContain("2 of 3 entries have no likelihood, impact or tier");
    expect(t).toContain("so they are missing from the matrix");
  });

  it("one synthesis batch of one", async () => {
    const t = await textOf("risk-batches-failed", {
      batches_total: 1,
      batches_failed: 1,
    });
    expect(t).toContain("1 of 1 synthesis batch failed");
  });

  it("entries lost before storage, against a one-entry intent", async () => {
    const t = await textOf("risk-entries-lost", {
      entries_intended: 1,
      entries_total: 0,
      entries_without_tier: 0,
      entries: [],
    });
    expect(t).toContain("1 of 1 entry did not reach storage");
  });

  it("one entry predating link recording", async () => {
    const t = await textOf("risk-entries-links-not-recorded", {
      entries_total: 1,
      entries_without_tier: 0,
      entries_links_not_recorded: 1,
    });
    expect(t).toContain("1 of 1 entry predates link recording");
  });

  it("citations across a one-entry register", async () => {
    const t = await textOf("risk-citations-dropped", {
      entries_total: 1,
      entries_without_tier: 0,
      dropped_citations: 0,
    });
    expect(t).toContain("across the 1 entry.");
    expect(t).not.toContain("1 entries");
  });
});
