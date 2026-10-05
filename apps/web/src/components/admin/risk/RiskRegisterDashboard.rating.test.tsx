import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as riskClient from "@/lib/risk/client";
import type { RiskEntry, RiskGate, RiskRegister } from "@/lib/risk/types";

import { RiskRegisterDashboard } from "./RiskRegisterDashboard";

/**
 * #844: the consultant rates an entry the model left unrated.
 *
 * The page only renders and sends; the api derives the tier. So these tests
 * pin what is SENT (the exact body, including `null` to clear) and that the
 * page renders the register the api RETURNS, never a locally patched copy.
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

const editRiskEntryRating = vi.mocked(riskClient.editRiskEntryRating);
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

describe("RiskRegisterDashboard consultant rating (#844)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getActiveClientId.mockResolvedValue("c1");
    getClientName.mockResolvedValue("Client");
    fetchRiskGate.mockResolvedValue(gate());
  });

  it("shows an unrated entry as Not rated, never in the Negligible colour", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(register());
    await loaded();
    expect(screen.getByTestId("risk-tier-not-rated").textContent).toBe(
      "Not rated",
    );
  });

  it("sends the chosen likelihood alone, and renders the register the api returns", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(register());
    editRiskEntryRating.mockResolvedValue(
      register({
        entries_without_tier: 0,
        entries: [
          entry({
            likelihood: "high",
            impact: "catastrophic",
            tier: "critical",
            rating_edited_by: "u1",
            rating_edited_at: "2026-10-04T01:00:00Z",
          }),
        ],
      }),
    );
    await loaded();

    fireEvent.change(
      screen.getByRole("combobox", { name: "Likelihood for Credential theft" }),
      { target: { value: "high" } },
    );

    await waitFor(() =>
      expect(
        screen.getByText("Rating edited by consultant"),
      ).toBeInTheDocument(),
    );
    expect(editRiskEntryRating).toHaveBeenCalledWith("c1", "e1", {
      likelihood: "high",
    });
    // The tier comes from the RESPONSE: the page never derives one itself.
    expect(screen.getByText("Critical")).toBeInTheDocument();
    expect(screen.queryByTestId("risk-tier-not-rated")).toBeNull();
    expect(screen.queryByTestId("risk-entries-without-tier")).toBeNull();
  });

  it("sends null when the consultant chooses Not rated", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(
      register({
        entries_without_tier: 0,
        entries: [
          entry({ likelihood: "low", impact: "minor", tier: "negligible" }),
        ],
      }),
    );
    editRiskEntryRating.mockResolvedValue(register());
    await loaded();

    fireEvent.change(
      screen.getByRole("combobox", { name: "Impact for Credential theft" }),
      { target: { value: "" } },
    );
    await waitFor(() =>
      expect(editRiskEntryRating).toHaveBeenCalledWith("c1", "e1", {
        impact: null,
      }),
    );
  });

  it("shows the api's refusal and keeps the stored rating", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(register());
    editRiskEntryRating.mockRejectedValue(new Error("refused by the api"));
    await loaded();

    fireEvent.change(
      screen.getByRole("combobox", { name: "Likelihood for Credential theft" }),
      { target: { value: "low" } },
    );
    await waitFor(() =>
      expect(screen.getByText("Error: refused by the api")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("risk-tier-not-rated")).toBeInTheDocument();
  });

  it("offers no rating control once the register is exported", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(
      register({ finalized_at: "2026-10-04T02:00:00Z" }),
    );
    await loaded();
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(
      screen.getByText(
        /This version has been exported, so its ratings are fixed/,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Not rated × Not rated")).toBeInTheDocument();
  });

  it("names the edit, not a regenerate, as the remedy for unrated entries", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(register());
    await loaded();
    const alert = screen.getByTestId("risk-entries-without-tier");
    expect(alert.textContent).toMatch(/1 of 1/);
    expect(alert.textContent).toMatch(
      /Set a likelihood and impact on each in the Register table below/,
    );
    expect(alert.textContent).not.toMatch(/Regenerate/);
  });

  it("names no edit remedy once the selects are gone (#854 review, F5)", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(
      register({ finalized_at: "2026-10-04T02:00:00Z" }),
    );
    await loaded();
    const alert = screen.getByTestId("risk-entries-without-tier");
    expect(alert.textContent).toMatch(/1 of 1/);
    expect(alert.textContent).not.toMatch(/Set a likelihood and impact/);
  });

  it("shows no consultant marker on a fully cleared rating (#854 review, F2)", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(
      register({
        entries: [
          entry({
            likelihood: null,
            impact: null,
            tier: null,
            rating_edited_by: "u1",
            rating_edited_at: "2026-10-04T01:00:00Z",
          }),
        ],
      }),
    );
    await loaded();
    expect(screen.queryByText("Rating edited by consultant")).toBeNull();
  });

  it("marks a half-set rating as edited by the consultant (ruling (a))", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(
      register({
        entries: [
          entry({
            likelihood: "medium",
            impact: null,
            tier: null,
            rating_edited_by: "u1",
            rating_edited_at: "2026-10-04T01:00:00Z",
          }),
        ],
      }),
    );
    await loaded();
    expect(screen.getByText("Rating edited by consultant")).toBeInTheDocument();
  });

  it("warns before regenerating when the version holds consultant ratings (#854 F3)", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(
      register({
        entries: [
          entry({
            likelihood: "low",
            impact: "minor",
            tier: "negligible",
            rating_edited_by: "u1",
            rating_edited_at: "2026-10-04T01:00:00Z",
          }),
        ],
      }),
    );
    await loaded();
    expect(
      screen.getByTestId("risk-regenerate-carries-ratings").textContent,
    ).toBe(
      "Regenerating drafts a new version. Consultant ratings carry over to the entry for the same finding; any that cannot be matched are listed after, to rate again.",
    );
  });

  it("does not warn when no rating was edited", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(register());
    await loaded();
    expect(screen.queryByTestId("risk-regenerate-carries-ratings")).toBeNull();
  });

  it("says what a regenerate carried over and what it could not (#854 F3)", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(
      register({
        ratings_carried_recorded: true,
        ratings_carried: 2,
        ratings_carried_from_version: 3,
        ratings_not_carried: ["T1003"],
      }),
    );
    await loaded();
    expect(screen.getByTestId("risk-ratings-carried").textContent).toBe(
      "2 consultant ratings were carried over from version 3. 1 could not be matched to an entry in this version and was not carried: T1003. Rate it again in the Register table.",
    );
  });

  it("states findings with no entry and with several, in number", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(
      register({
        findings_recorded: true,
        findings_total: 3,
        findings_without_entry: ["GV.OC-01"],
        findings_with_several_entries: { T1078: 2, T1003: 2 },
      }),
    );
    await loaded();
    const note = screen.getByTestId("risk-findings-coverage");
    expect(note.textContent).toMatch(
      /Of 3 findings, 1 has no entry and 2 have more than one/,
    );
  });

  it("says nothing about findings when nothing was recorded", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(
      register({ findings_recorded: false }),
    );
    await loaded();
    expect(screen.queryByTestId("risk-findings-coverage")).toBeNull();
  });
});
