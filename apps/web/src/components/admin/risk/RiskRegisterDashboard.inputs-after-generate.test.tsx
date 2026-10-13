import "@testing-library/jest-dom/vitest";

import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as clientReads from "@/lib/admin/client-reads";
import * as riskClient from "@/lib/risk/client";
import type { RiskEntry, RiskGate, RiskRegister } from "@/lib/risk/types";

import { RiskRegisterDashboard } from "./RiskRegisterDashboard";

/**
 * RR-1 (for #1122), review finding 2 on #1148: the Inputs panel's split comes
 * from the GATE (`in_register`, computed against the register on screen), so
 * after Generate the gate is re-read. Without that, v2 generated with a
 * different selection shows v1's split until the page is reloaded.
 */

vi.mock("@/lib/risk/client", () => ({
  describeRiskError: (e: unknown) => String(e),
  editRiskEntryRating: vi.fn(),
  exportRiskRegister: vi.fn(),
  fetchRiskGate: vi.fn(),
  fetchRiskRegisterLatest: vi.fn(),
  generateRiskRegister: vi.fn(),
}));

// RR-2 (for #1121): the page takes its client from its own picker. The two
// reads are mocked where they live, with API-shaped bodies, so the real
// resolver chooses the client. The URL carries no ?client=.
vi.mock("next/navigation", () => ({
  usePathname: () => "/admin/risk-register",
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/lib/admin/client-reads", () => ({
  readClientList: vi.fn(),
  readActiveClient: vi.fn(),
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

/**
 * RR-2 (for #1121): `id` is the one listed client, named `name`, and the one
 * saved in this browser. The list is shaped like `AdminClientListResponse`.
 */
function mockPickedClient(id: string, name: string): void {
  vi.mocked(clientReads.readClientList).mockResolvedValue({
    clients: [
      {
        id,
        legal_name: name,
        dba_name: null,
        industry: null,
        size_band: null,
        intake_completed_at: null,
        created_at: "2026-10-01T00:00:00Z",
        archived_at: null,
        open_request_count: 0,
        total_request_count: 0,
      },
    ],
  });
  vi.mocked(clientReads.readActiveClient).mockResolvedValue({ active: id });
}

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
  await waitFor(() => {
    // RR-2 (for #1121): the h1 names the client and renders before the
    // body has loaded, so the wait is for the body too.
    expect(
      screen.getByRole("heading", { name: /^Risk Register for / }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Loading…")).toBeNull();
  });
}

function zt(inRegister: "input" | "deselected"): RiskGate["inputs"][number] {
  return {
    kind: "zt",
    engaged: true,
    status: "approved",
    version: 1,
    qualifier: null,
    in_register: inRegister,
  };
}

function gateWith(inRegister: "input" | "deselected"): RiskGate {
  return {
    ...gate(),
    eligible: [
      {
        kind: "attack",
        service_id: "svc-attack",
        title: "ATT&CK",
        framework: null,
        label: "ATT&CK coverage",
      },
      {
        kind: "csf",
        service_id: "svc-csf",
        title: "CSF",
        framework: null,
        label: "NIST CSF",
      },
      {
        kind: "zt",
        service_id: "svc-zt",
        title: "ZT",
        framework: "cisa_ztmm_2_0",
        label: "Zero Trust (CISA ZTMM 2.0)",
      },
    ],
    ineligible: [],
    inputs: [
      {
        kind: "attack",
        engaged: true,
        status: "approved",
        version: 1,
        in_register: "input",
      },
      zt(inRegister),
    ],
  };
}

describe("the Inputs panel after Generate (RR-1, #1148 finding 2)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPickedClient("c1", "Client");
  });

  it("re-reads the gate, so a v2 with Zero Trust left out moves it under copy 13", async () => {
    // v1 drew on Zero Trust; the admin unticks it and generates v2.
    fetchRiskRegisterLatest.mockResolvedValue(register({ version: 1 }));
    fetchRiskGate
      .mockResolvedValueOnce(gateWith("input"))
      .mockResolvedValueOnce(gateWith("deselected"));
    vi.mocked(riskClient.generateRiskRegister).mockResolvedValue(
      register({ version: 2 }),
    );
    await loaded();
    // The positive state first: before Generate, ZT is an input.
    expect(screen.getByTestId("risk-register-inputs")).toBeInTheDocument();
    expect(screen.queryByTestId("risk-register-not-in-register")).toBeNull();

    fireEvent.click(
      screen.getByRole("checkbox", { name: "Zero Trust (CISA ZTMM 2.0)" }),
    );
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Regenerate" }));
    });

    await waitFor(() => expect(fetchRiskGate).toHaveBeenCalledTimes(2));
    const out = await screen.findByTestId("risk-register-not-in-register");
    expect(
      Array.from(out.querySelectorAll("li")).map((li) => li.textContent),
    ).toEqual(["Zero Trust: left out of this register"]);
  });
});
