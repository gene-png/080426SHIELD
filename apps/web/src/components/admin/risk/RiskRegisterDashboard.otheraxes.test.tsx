import "@testing-library/jest-dom/vitest";

import { render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as clientReads from "@/lib/admin/client-reads";
import * as riskClient from "@/lib/risk/client";
import type { RiskEntry, RiskGate, RiskRegister } from "@/lib/risk/types";

import { RiskRegisterDashboard } from "./RiskRegisterDashboard";

/**
 * #736 6094620397, Risk E item 4, on the admin Risk screen: a column headed
 * "Other axes"; comma-joined display names; an empty cell for `[]`; "Not
 * recorded" for NULL. Expected strings written out from the ruling.
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
    inputs: [],
  };
}

function entry(
  id: string,
  title: string,
  other_axes: string[] | null,
): RiskEntry {
  return {
    id,
    title,
    description: null,
    axis: "detection",
    other_axes,
    source: "coverage_finding",
    source_id: "T1078",
    linked_techniques: [],
    linked_controls: [],
    likelihood: "high",
    impact: "major",
    tier: "high",
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
  };
}

function register(entries: RiskEntry[]): RiskRegister {
  return {
    batches_total: null,
    batches_failed: null,
    entries_intended: null,
    excluded_inputs: [],
    excluded_inputs_recorded: true,
    entries_total: entries.length,
    entries_without_tier: 0,
    entries_with_dropped_links: 0,
    entries_unlinked_after_drops: 0,
    entries_links_not_recorded: 0,
    excluded_unscored_links: [],
    excluded_unscored_links_recorded: false,
    dropped_citations: 0,
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
    created_at: "2026-10-10T00:00:00Z",
    xlsx_artifact_id: null,
    pdf_artifact_id: null,
    docx_artifact_id: null,
    xlsx_filename: null,
    pdf_filename: null,
    docx_filename: null,
    entries,
    tier_counts: { high: entries.length },
    axis_counts: { detection: entries.length },
    action_counts: { remediate: entries.length },
  };
}

function cellUnder(header: string, title: string): string {
  const row = screen.getByText(title).closest("tr");
  if (row === null) throw new Error(`no table row for ${title}`);
  const table = row.closest("table");
  if (table === null) throw new Error(`no table for ${title}`);
  const headers = within(table)
    .getAllByRole("columnheader")
    .map((h) => h.textContent);
  const at = headers.indexOf(header);
  if (at === -1)
    throw new Error(`no "${header}" column among ${headers.join(" | ")}`);
  return row.querySelectorAll("td")[at]?.textContent ?? "";
}

describe("RiskRegisterDashboard other axes (#474 E item 4)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPickedClient("c1", "Client");
    fetchRiskGate.mockResolvedValue(gate());
  });

  it("renders each of the three states under an Other axes heading", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(
      register([
        entry("e1", "Listed risk", ["prevention", "response"]),
        entry("e2", "Empty risk", []),
        entry("e3", "Unrecorded risk", null),
      ]),
    );
    render(<RiskRegisterDashboard />);
    // What must appear first: the heading and a populated cell.
    await waitFor(() =>
      expect(
        screen.getByRole("columnheader", { name: "Other axes" }),
      ).toBeInTheDocument(),
    );
    expect(cellUnder("Other axes", "Listed risk")).toBe("Prevention, Response");
    expect(cellUnder("Other axes", "Empty risk")).toBe("");
    expect(cellUnder("Other axes", "Unrecorded risk")).toBe("Not recorded");
  });
});
