import "@testing-library/jest-dom/vitest";

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as riskClient from "@/lib/risk/client";
import type { RiskEntry, RiskGate, RiskRegister } from "@/lib/risk/types";

import { RiskRegisterDashboard } from "./RiskRegisterDashboard";

/**
 * #415: the consultant's scored-coverage banner counts the ATT&CK techniques
 * pending review apart from the unscored rows (C3's count clause, #736
 * 6069843323), and says when a register predates the count (ruling (b),
 * 6072976838). Expected text is the approved copy, verbatim.
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

const NOT_RECORDED =
  "Whether any linked technique was pending review was not recorded for this register.";

function scoped(attackPending: number | null): RiskRegister {
  return register({
    excluded_unscored_links_recorded: true,
    excluded_unscored_links: [
      {
        service: "attack",
        scored: 12,
        total: 700,
        pending_review: attackPending,
      },
      { service: "zt", scored: 2, total: 37, pending_review: null },
    ],
  });
}

function banner(): HTMLElement {
  return screen.getByTestId("risk-link-scope");
}

describe("RiskRegisterDashboard pending review (#415)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getActiveClientId.mockResolvedValue("c1");
    getClientName.mockResolvedValue("Client");
    fetchRiskGate.mockResolvedValue(gate());
  });

  it("counts the ATT&CK techniques pending review apart from the unscored", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(scoped(3));
    await loaded();
    const items = [...banner().querySelectorAll("li")].map(
      (li) => li.textContent,
    );
    expect(items).toEqual([
      "ATT&CK coverage: 12 of 700 scored, 688 not yet judged and therefore not citable, and 3 pending review and therefore not citable",
      "Zero Trust: 2 of 37 scored, 35 not yet judged and therefore not citable",
    ]);
    expect(banner().textContent).not.toContain(NOT_RECORDED);
  });

  it("adds nothing when none are pending", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(scoped(0));
    await loaded();
    expect(banner().textContent).toContain("ATT&CK coverage: 12 of 700 scored");
    expect(banner().textContent).not.toContain("pending review");
  });

  it("says the count was not recorded for a register that predates it", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(scoped(null));
    await loaded();
    expect(banner().textContent).toContain("ATT&CK coverage: 12 of 700 scored");
    expect(banner().textContent).toContain(NOT_RECORDED);
    expect(banner().textContent).not.toContain("pending review and therefore");
  });
});

describe("RiskRegisterDashboard dropped-link banners name pending review (#415)", () => {
  // The wording approved verbatim on #736: a dropped value has a third cause.
  beforeEach(() => {
    vi.clearAllMocks();
    getActiveClientId.mockResolvedValue("c1");
    getClientName.mockResolvedValue("Client");
    fetchRiskGate.mockResolvedValue(gate());
  });

  it("the unlinked-entries banner names all three causes", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(
      register({
        entries_total: 4,
        entries_unlinked_after_drops: 1,
        entries_with_dropped_links: 1,
      }),
    );
    await loaded();
    const text = (
      screen.getByTestId("risk-entries-unlinked-after-drops").textContent ?? ""
    ).replace(/\s+/g, " ");
    expect(text).toContain(
      "Every value the model sent was misnamed, names a control this client's assessments have not scored, or names an ATT&CK technique pending review.",
    );
    expect(text).toContain(
      "Where the cause is unscored or pending-review assessment work rather than a misnamed value, regenerating returns the same rows and spends another model call.",
    );
  });

  it("the still-linked banner names all three causes", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(
      register({
        entries_total: 4,
        entries_unlinked_after_drops: 0,
        entries_with_dropped_links: 1,
      }),
    );
    await loaded();
    const text = (
      screen.getByTestId("risk-entries-with-dropped-links").textContent ?? ""
    ).replace(/\s+/g, " ");
    expect(text).toContain(
      "Worth a look before the next run: each is a value the model misnamed, a control nobody has scored yet, or an ATT&CK technique pending review.",
    );
  });
});
