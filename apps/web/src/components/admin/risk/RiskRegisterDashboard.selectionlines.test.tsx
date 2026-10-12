import "@testing-library/jest-dom/vitest";

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as clientReads from "@/lib/admin/client-reads";
import * as riskClient from "@/lib/risk/client";
import type { RiskEntry, RiskGate, RiskRegister } from "@/lib/risk/types";

import { RiskRegisterDashboard } from "./RiskRegisterDashboard";

/**
 * RR-1 (for #1122), on the admin screen: the selection lines (design note
 * §6.1, copy 8, 9a-9c and 11) above the target lines, the target rows' and
 * scored-coverage rows' server `label` (§6.2, A8), and the Inputs panel split
 * (§6.5, copies 13-15). Expected strings are §8's, verbatim. The harness is
 * the baseline test's.
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

const COPY_11 =
  "This register has no usable record of how its services were chosen or which were left out.";

function selectionLineTexts(): string[] {
  return Array.from(
    screen.getByTestId("risk-selection-lines").querySelectorAll("p"),
  ).map((p) => p.textContent ?? "");
}

describe("RiskRegisterDashboard, what the register was generated from (RR-1)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPickedClient("c1", "Client");
    fetchRiskGate.mockResolvedValue(gate());
  });

  it.each([
    ["absent", {}],
    [
      "false",
      { selection_recorded: false, covered_inputs: ["ATT&CK coverage"] },
    ],
  ])("prints copy 11 alone when selection_recorded is %s", async (_n, over) => {
    fetchRiskRegisterLatest.mockResolvedValue(register(over));
    await loaded();
    expect(selectionLineTexts()).toEqual([COPY_11]);
  });

  it("prints copy 8, 9b and 9c, in that order", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(
      register({
        selection_recorded: true,
        covered_inputs: ["ATT&CK coverage", "NIST CSF"],
        deselected_inputs: ["Zero Trust (CISA ZTMM 2.0)", "Other"],
        ineligible_inputs: ["Zero Trust (DoD ZT Reference Architecture)"],
      }),
    );
    await loaded();
    expect(selectionLineTexts()).toEqual([
      "This register was generated from ATT&CK coverage and NIST CSF.",
      "Zero Trust (CISA ZTMM 2.0) and Other were not included in this register.",
      "Zero Trust (DoD ZT Reference Architecture) was engaged but had no assessment when this register was generated, so it is not in this register.",
    ]);
  });

  it("prints the lines above the target lines", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(register());
    await loaded();
    const sel = screen.getByTestId("risk-selection-lines");
    const targets = screen.getByTestId("risk-targets-used");
    expect(
      sel.compareDocumentPosition(targets) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("names the framework on the A8 register's one ZT target row, from its label", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(
      register({
        selection_recorded: true,
        covered_inputs: ["ATT&CK coverage", "Zero Trust (CISA ZTMM 2.0)"],
        ineligible_inputs: ["Zero Trust (DoD ZT Reference Architecture)"],
        targets: [
          {
            kind: "zt",
            framework: "cisa_ztmm_2_0",
            target: 4,
            source: "client",
            origin: "live_at_generate",
            label: "Zero Trust (CISA ZTMM 2.0)",
          },
        ],
        targets_recorded: true,
      }),
    );
    await loaded();
    expect(screen.getByTestId("risk-targets-used").textContent).toBe(
      "Zero Trust (CISA ZTMM 2.0) findings are measured against target stage 4, the engagement target when this register was generated.",
    );
  });

  it("names each scored-coverage row by the server's label", async () => {
    // A bare `zt` key the server resolved to a named framework (A8): the web
    // has no label table, so only the server's `label` can produce this.
    fetchRiskRegisterLatest.mockResolvedValue(
      register({
        excluded_unscored_links_recorded: true,
        excluded_unscored_links: [
          {
            service: "zt",
            label: "Zero Trust (CISA ZTMM 2.0)",
            scored: 3,
            total: 5,
          },
        ],
      }),
    );
    await loaded();
    const banner = screen.getByTestId("risk-link-scope");
    expect(banner.textContent).toContain(
      "Zero Trust (CISA ZTMM 2.0): 3 of 5 scored",
    );
  });
});

describe("the Inputs panel split (RR-1, design note §6.5)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPickedClient("c1", "Client");
    fetchRiskRegisterLatest.mockResolvedValue(register());
  });

  it("moves deselected and ineligible rows under copy 13, with no status", async () => {
    fetchRiskGate.mockResolvedValue({
      ...gate(),
      inputs: [
        {
          kind: "attack",
          engaged: true,
          status: "released",
          version: 1,
          in_register: "input",
        },
        {
          kind: "zt",
          engaged: true,
          status: "in_progress",
          version: 1,
          qualifier: "CISA ZTMM 2.0",
          in_register: "deselected",
        },
        {
          kind: "zt",
          engaged: true,
          status: null,
          version: null,
          qualifier: "DoD ZT Reference Architecture",
          in_register: "ineligible",
        },
        {
          kind: "csf",
          engaged: false,
          status: null,
          version: null,
          in_register: null,
        },
      ],
    });
    await loaded();
    const panel = screen.getByTestId("risk-register-inputs");
    const out = screen.getByTestId("risk-register-not-in-register");
    expect(out.querySelector("p")?.textContent).toBe("Not in this register");
    expect(
      Array.from(out.querySelectorAll("li")).map((li) => li.textContent),
    ).toEqual([
      "Zero Trust (CISA ZTMM 2.0): left out of this register",
      "Zero Trust (DoD ZT Reference Architecture): no assessment when this register was generated",
    ]);
    // The rows under the rule: the input and the not-engaged kind, and
    // neither of the two above.
    const ruled = Array.from(panel.querySelectorAll(":scope > ul > li")).map(
      (li) => li.textContent ?? "",
    );
    expect(ruled).toHaveLength(2);
    expect(ruled[0]).toMatch(/^ATT&CK coverage: /);
    expect(ruled[1]).toBe("NIST CSF: not engaged");
    // "in progress" never appears beside a service that does not hold the
    // register in draft.
    expect(out.textContent).not.toMatch(/progress|draft/i);
  });

  it("shows no second group when every row is an input or unqualified", async () => {
    fetchRiskGate.mockResolvedValue({
      ...gate(),
      inputs: [
        {
          kind: "attack",
          engaged: true,
          status: "released",
          version: 1,
          in_register: "input",
        },
        {
          kind: "zt",
          engaged: true,
          status: "released",
          version: 1,
          in_register: null,
        },
      ],
    });
    await loaded();
    expect(screen.getByTestId("risk-register-inputs")).toBeInTheDocument();
    expect(screen.queryByTestId("risk-register-not-in-register")).toBeNull();
  });
});
