import "@testing-library/jest-dom/vitest";

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as riskClient from "@/lib/risk/client";
import type { RiskEntry, RiskGate, RiskRegister } from "@/lib/risk/types";

import { RiskRegisterDashboard } from "./RiskRegisterDashboard";

/**
 * #876: the register draws on every engaged service. With two Zero Trust
 * services the Inputs rows and the scored-coverage rows name the framework
 * (advisor, #736 6019425290 Q3); two services of one kind and framework would
 * produce the same findings, so the gate's sentence shows and Generate is not
 * offered (Q2 (a)). Fixtures copied from the publish suite.
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

const DUPLICATE =
  "Two engaged services of the same kind would produce the same findings: ZT and ZT 2. The register cannot be generated while both are engaged.";

describe("RiskRegisterDashboard per service (#876)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getActiveClientId.mockResolvedValue("c1");
    getClientName.mockResolvedValue("Client");
    fetchRiskRegisterLatest.mockResolvedValue(null);
  });

  it("names each Zero Trust framework on the Inputs panel", async () => {
    fetchRiskGate.mockResolvedValue({
      ...gate(),
      inputs: [
        {
          kind: "zt",
          engaged: true,
          status: "released",
          version: 1,
          qualifier: "CISA ZTMM 2.0",
        },
        {
          kind: "zt",
          engaged: true,
          status: "draft",
          version: 1,
          qualifier: "DoD ZT Reference Architecture",
        },
      ],
    });
    await loaded();
    const panel = screen.getByTestId("risk-register-inputs");
    expect(panel).toHaveTextContent("Zero Trust (CISA ZTMM 2.0): released");
    expect(panel).toHaveTextContent(
      "Zero Trust (DoD ZT Reference Architecture): in progress (draft)",
    );
  });

  it("shows the duplicate sentence and does not offer Generate", async () => {
    fetchRiskGate.mockResolvedValue({ ...gate(), duplicate_inputs: DUPLICATE });
    await loaded();
    expect(
      screen.getByTestId("risk-register-duplicate-inputs"),
    ).toHaveTextContent(DUPLICATE);
    expect(screen.getByRole("button", { name: "Generate" })).toBeDisabled();
  });

  it("offers Generate when there is no duplicate", async () => {
    fetchRiskGate.mockResolvedValue({ ...gate(), duplicate_inputs: null });
    await loaded();
    expect(screen.getByRole("button", { name: "Generate" })).toBeEnabled();
    expect(screen.queryByTestId("risk-register-duplicate-inputs")).toBeNull();
  });

  it("labels each Zero Trust framework's scored-coverage row", async () => {
    fetchRiskGate.mockResolvedValue(gate());
    fetchRiskRegisterLatest.mockResolvedValue(
      register({
        excluded_unscored_links_recorded: true,
        excluded_unscored_links: [
          { service: "attack", scored: 3, total: 10 },
          { service: "zt:cisa_ztmm_2_0", scored: 2, total: 37 },
          { service: "zt:dod_ztra", scored: 1, total: 20 },
        ],
      }),
    );
    await loaded();
    expect(screen.getByText(/ATT&CK coverage: 3 of/)).toBeInTheDocument();
    expect(
      screen.getByText(/Zero Trust \(CISA ZTMM 2\.0\): 2 of/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Zero Trust \(DoD ZT Reference Architecture\): 1 of/),
    ).toBeInTheDocument();
  });
});
