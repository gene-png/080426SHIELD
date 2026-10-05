import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as riskClient from "@/lib/risk/client";
import type { RiskEntry, RiskGate, RiskRegister } from "@/lib/risk/types";

import { RiskRegisterDashboard } from "./RiskRegisterDashboard";

/**
 * #737: Publish is the one action that puts a register on the client's
 * dashboard. Offered only for an unpublished version, and not while an entry
 * is unrated (#844 D1), which the api refuses as well.
 */

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

const publishRiskRegister = vi.mocked(riskClient.publishRiskRegister);
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

describe("RiskRegisterDashboard publish (#737)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getActiveClientId.mockResolvedValue("c1");
    getClientName.mockResolvedValue("Client");
    fetchRiskGate.mockResolvedValue(gate());
  });

  const rated = entry({
    likelihood: "low",
    impact: "minor",
    tier: "negligible",
  });

  it("publishes and then shows the register as published, with no Publish button", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(
      register({ entries_without_tier: 0, entries: [rated] }),
    );
    publishRiskRegister.mockResolvedValue(
      register({
        entries_without_tier: 0,
        entries: [rated],
        finalized_at: "2026-10-04T03:00:00Z",
      }),
    );
    await loaded();
    expect(screen.getByText(/not published to the client/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Publish to client" }));

    await waitFor(() =>
      expect(screen.getByText(/· published to the client/)).toBeInTheDocument(),
    );
    expect(publishRiskRegister).toHaveBeenCalledWith("c1");
    expect(
      screen.queryByRole("button", { name: "Publish to client" }),
    ).toBeNull();
  });

  it("does not offer Publish while an entry is unrated", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(register());
    await loaded();
    expect(
      screen.getByRole("button", { name: "Publish to client" }),
    ).toBeDisabled();
  });

  it("shows the api's refusal", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(
      register({ entries_without_tier: 0, entries: [rated] }),
    );
    publishRiskRegister.mockRejectedValue(new Error("refused by the api"));
    await loaded();
    fireEvent.click(screen.getByRole("button", { name: "Publish to client" }));
    await waitFor(() =>
      expect(screen.getByText("Error: refused by the api")).toBeInTheDocument(),
    );
    expect(screen.getByText(/not published to the client/)).toBeInTheDocument();
  });
});

describe("RiskRegisterDashboard inputs and draft labels (#737)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getActiveClientId.mockResolvedValue("c1");
    getClientName.mockResolvedValue("Client");
  });

  it("shows Gene's rule and every input's state", async () => {
    fetchRiskGate.mockResolvedValue({
      ...gate(),
      inputs: [
        { kind: "attack", engaged: true, status: "approved", version: 1 },
        { kind: "csf", engaged: false, status: null, version: null },
      ],
    });
    fetchRiskRegisterLatest.mockResolvedValue(register());
    await loaded();
    const panel = screen.getByTestId("risk-register-inputs");
    expect(panel.textContent).toContain(
      "This register is a draft until every assessment it draws on is final.",
    );
    expect(panel.textContent).toContain(
      "ATT&CK coverage: approved, not yet released",
    );
    expect(panel.textContent).toContain("NIST CSF: not engaged");
  });

  it("labels an entry drafted from an unreleased input", async () => {
    fetchRiskGate.mockResolvedValue(gate());
    fetchRiskRegisterLatest.mockResolvedValue(
      register({ entries: [entry({ source_state: "draft" })] }),
    );
    await loaded();
    expect(
      screen.getByText("T1078 (from a draft assessment)"),
    ).toBeInTheDocument();
  });
});
