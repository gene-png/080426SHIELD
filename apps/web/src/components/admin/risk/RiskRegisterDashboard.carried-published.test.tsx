import "@testing-library/jest-dom/vitest";

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as riskClient from "@/lib/risk/client";
import type { RiskEntry, RiskGate, RiskRegister } from "@/lib/risk/types";

import { RiskRegisterDashboard } from "./RiskRegisterDashboard";

/**
 * #930, option A (#736 6067815887): on a PUBLISHED version the carried-ratings
 * block drops the "Rate it/them again" imperative, because the Register table's
 * selects are gone (D-076), and keeps its amber style, because the ratings were
 * carried by the model and not re-rated (ruling (b)). The fixture is a state
 * generate and publish can produce: two entries for T1003, so a rating for it
 * is not carried as ambiguous, and every entry rated.
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
    // #737: required; the Inputs panel's rows.
    inputs: [],
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
    // #737: required; null = the finding's input was released.
    source_state: null,
    source_review_pending: false,
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
    // #854 F3: not recorded, for the same reason as the findings fields.
    ratings_carried_recorded: false,
    ratings_carried: null,
    ratings_carried_from_version: null,
    ratings_not_carried: [],
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

const PUBLISHED_LINE =
  "1 rating could not be carried because this version or the last has more than one entry for the same finding: T1003.";
const DRAFT_LINE =
  "1 rating could not be carried because this version or the last has more than one entry for the same finding: T1003. Rate it again in the Register table.";

function carried(finalizedAt: string | null): RiskRegister {
  return register({
    finalized_at: finalizedAt,
    // Reachable: `_carry_ratings` records "ambiguous" only when this version
    // or the last has more than one entry for the finding (here two T1003
    // entries), and "no_entry" when it has none. Every entry is rated, which
    // publish requires.
    entries_total: 3,
    entries_without_tier: 0,
    entries: [
      entry({ likelihood: "high", impact: "major", tier: "high" }),
      entry({
        id: "e2",
        title: "Credential dumping from LSASS",
        source_id: "T1003",
        likelihood: "medium",
        impact: "major",
        tier: "medium",
      }),
      entry({
        id: "e3",
        title: "Credential dumping from the SAM database",
        source_id: "T1003",
        likelihood: "medium",
        impact: "moderate",
        tier: "medium",
      }),
    ],
    ratings_carried_recorded: true,
    ratings_carried: 0,
    ratings_carried_from_version: 1,
    ratings_not_carried: [{ key: "T1003", reason: "ambiguous" }],
  });
}

function block(): HTMLElement {
  return screen.getByTestId("risk-ratings-carried");
}

describe("RiskRegisterDashboard carried ratings on a published version (#930)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getActiveClientId.mockResolvedValue("c1");
    getClientName.mockResolvedValue("Client");
    fetchRiskGate.mockResolvedValue(gate());
  });

  it("drops the imperative and keeps the amber style", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(carried("2026-10-09T00:00:00Z"));
    await loaded();
    const lines = [...block().querySelectorAll("p")].map((p) => p.textContent);
    expect(lines).toEqual([
      "0 consultant ratings were carried over from version 1.",
      PUBLISHED_LINE,
    ]);
    expect(block().textContent).not.toMatch(/Rate|Register table/);
    expect(block().className).toContain("bg-status-warning-bg");
    // The control the draft sentence names is gone here.
    expect(screen.queryByRole("combobox", { name: /Likelihood/ })).toBeNull();
  });

  it("keeps the imperative on a draft, where the control exists", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(carried(null));
    await loaded();
    const lines = [...block().querySelectorAll("p")].map((p) => p.textContent);
    expect(lines).toEqual([
      "0 consultant ratings were carried over from version 1.",
      DRAFT_LINE,
    ]);
    expect(
      screen.getByRole("combobox", { name: "Likelihood for Credential theft" }),
    ).toBeInTheDocument();
  });
});
