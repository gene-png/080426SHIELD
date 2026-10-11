import "@testing-library/jest-dom/vitest";

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as riskClient from "@/lib/risk/client";
import type { RiskEntry, RiskGate, RiskRegister } from "@/lib/risk/types";

import { RiskRegisterDashboard } from "./RiskRegisterDashboard";

/**
 * Ruling #736 6104067136 (see #1033): the consultant's register states the
 * same three CSF Playbook results the files do. Where scores and targets
 * never shared a row (`csf_no_shared_row`, read by the files' reader), R11's
 * line; the true no-scores case and a register predating the field (absent)
 * keep the original line. Fixtures copied from the csfsource suite.
 */

const NO_SCORES =
  "NIST CSF was not measured for this register: the CSF Playbook has no scores.";
const NO_SHARED_ROW =
  "NIST CSF was not measured for this register: no CSF Playbook row has both a score and a target.";
const MEASURED =
  "NIST CSF findings are measured against each subcategory's target level in the CSF Playbook.";

vi.mock("@/lib/risk/client", () => ({
  describeRiskError: (e: unknown) => String(e),
  editRiskEntryRating: vi.fn(),
  publishRiskRegister: vi.fn(),
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

function csf(source: string): Partial<RiskRegister> {
  return {
    targets: [
      {
        kind: "csf",
        framework: null,
        target: null,
        source,
        origin: "live_at_generate",
      },
    ],
    targets_recorded: true,
  };
}

function lines(): string {
  return screen.getByTestId("risk-targets-used").textContent ?? "";
}

describe("RiskRegisterDashboard, the CSF Playbook's three results (#736 6104067136)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getActiveClientId.mockResolvedValue("c1");
    getClientName.mockResolvedValue("Client");
    fetchRiskGate.mockResolvedValue(gate());
  });

  it("no row with both a score and a target: R11's line", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(
      register({ ...csf("playbook_no_scores"), csf_no_shared_row: true }),
    );
    await loaded();
    expect(lines()).toContain(NO_SHARED_ROW);
    expect(lines()).not.toContain(NO_SCORES);
  });

  it("true no scores: the original line", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(
      register({ ...csf("playbook_no_scores"), csf_no_shared_row: false }),
    );
    await loaded();
    expect(lines()).toContain(NO_SCORES);
    expect(lines()).not.toContain(NO_SHARED_ROW);
  });

  it("a response predating the field: the original line", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(
      register(csf("playbook_no_scores")),
    );
    await loaded();
    expect(lines()).toContain(NO_SCORES);
    expect(lines()).not.toContain(NO_SHARED_ROW);
  });

  it("measured: the measured line, neither not-measured line", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(
      register({ ...csf("playbook"), csf_no_shared_row: false }),
    );
    await loaded();
    expect(lines()).toContain(MEASURED);
    expect(lines()).not.toContain(NO_SCORES);
    expect(lines()).not.toContain(NO_SHARED_ROW);
  });
});
