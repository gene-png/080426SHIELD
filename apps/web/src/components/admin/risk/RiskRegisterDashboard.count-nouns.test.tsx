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

/**
 * The stored entries agree with the counts, as `_serialize` derives them:
 * `entries_total` rows, the first `entries_without_tier` of them unrated.
 */
function consistent(over: Partial<RiskRegister>): Partial<RiskRegister> {
  const total = over.entries_total ?? 1;
  const unrated = over.entries_without_tier ?? 1;
  const entries = Array.from({ length: total }, (_, i) =>
    i < unrated
      ? entry({ id: `e${i}` })
      : entry({
          id: `e${i}`,
          likelihood: "high",
          impact: "major",
          tier: "high",
        }),
  );
  return { entries, ...over };
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
    fetchRiskRegisterLatest.mockResolvedValue(register(consistent(over)));
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

  // `_run_risk_synthesize_batched` re-raises when EVERY batch fails, so a
  // stored register has 1 <= batches_failed < batches_total: "1 of 1" cannot
  // be stored and is not built here.
  it("one synthesis batch of two failed", async () => {
    const t = await textOf("risk-batches-failed", {
      batches_total: 2,
      batches_failed: 1,
    });
    expect(t).toContain("1 of 2 synthesis batches failed");
    expect(t).toContain("the entries that batch would have produced");
    expect(t).not.toContain("those batches");
  });

  it("two synthesis batches of three failed", async () => {
    const t = await textOf("risk-batches-failed", {
      batches_total: 3,
      batches_failed: 2,
    });
    expect(t).toContain("2 of 3 synthesis batches failed");
    expect(t).toContain("the entries those batches would have produced");
  });

  // `generate`: an entry whose every proposed technique and control was
  // dropped. Such an entry is also counted in `entries_with_dropped_links`.
  it("one entry of two kept none of its links", async () => {
    const t = await textOf("risk-entries-unlinked-after-drops", {
      entries_total: 2,
      entries_without_tier: 0,
      entries_with_dropped_links: 1,
      entries_unlinked_after_drops: 1,
      dropped_citations: 1,
    });
    expect(t).toContain(
      "1 of 2 entries proposed ATT&CK or control links and kept none",
    );
    expect(t).toContain("so it shows no linkage at all");
    expect(t).toContain("sees that row as unlinked");
    expect(t).not.toContain("so they show");
  });

  it("two entries of three kept none of their links", async () => {
    const t = await textOf("risk-entries-unlinked-after-drops", {
      entries_total: 3,
      entries_without_tier: 0,
      entries_with_dropped_links: 2,
      entries_unlinked_after_drops: 2,
      dropped_citations: 2,
    });
    expect(t).toContain(
      "2 of 3 entries proposed ATT&CK or control links and kept none",
    );
    expect(t).toContain("so they show no linkage at all");
    expect(t).toContain("sees those rows as unlinked");
  });

  // `generate`: an entry that lost a value and kept a link.
  it("one entry of two lost a value and still shows linkage", async () => {
    const t = await textOf("risk-entries-with-dropped-links", {
      entries_total: 2,
      entries_without_tier: 0,
      entries_with_dropped_links: 1,
      entries_unlinked_after_drops: 0,
      dropped_citations: 1,
    });
    expect(t).toContain(
      "1 of 2 entries lost at least one value the model sent",
    );
    expect(t).toContain("the rest of it still resolved, so it shows linkage");
    expect(t).toContain("The values are on the entry");
  });

  // Three entries lost a value and one of them kept no link at all: the
  // banner counts the TWO that still show linkage, because the unlinked one
  // has its own banner and does not show linkage.
  it("counts only the entries that still show linkage", async () => {
    const t = await textOf("risk-entries-with-dropped-links", {
      entries_total: 4,
      entries_without_tier: 0,
      entries_with_dropped_links: 3,
      entries_unlinked_after_drops: 1,
      dropped_citations: 3,
    });
    expect(t).toContain(
      "2 of 4 entries lost at least one value the model sent",
    );
    expect(t).toContain(
      "the rest of each still resolved, so they show linkage",
    );
    expect(t).not.toContain("3 of 4");
  });

  // Rows written before migration 0048 carry `dropped_links` NULL
  // (`seed_demo.py` builds its entries that way). One register is written by
  // one generate, so either every entry predates the recording or none does.
  it("one entry predating link recording", async () => {
    const t = await textOf("risk-entries-links-not-recorded", {
      entries_total: 1,
      entries_without_tier: 0,
      entries_links_not_recorded: 1,
    });
    expect(t).toContain("1 of 1 entry predates link recording");
    expect(t).toContain("proposed linkage for it.");
    expect(t).not.toContain("for them");
  });

  it("three entries predating link recording", async () => {
    const t = await textOf("risk-entries-links-not-recorded", {
      entries_total: 3,
      entries_without_tier: 0,
      entries_links_not_recorded: 3,
    });
    expect(t).toContain("3 of 3 entries predate link recording");
    expect(t).toContain("proposed linkage for them.");
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
