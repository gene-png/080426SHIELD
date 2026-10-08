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

function rated(id: string, over: Partial<RiskEntry> = {}): RiskEntry {
  return entry({
    id,
    likelihood: "high",
    impact: "major",
    tier: "high",
    ...over,
  });
}

function droppedAny(e: RiskEntry): boolean {
  return e.dropped_links !== null && Object.keys(e.dropped_links).length > 0;
}

function droppedALink(e: RiskEntry): boolean {
  const d = e.dropped_links ?? {};
  return (
    (d.linked_techniques?.length ?? 0) > 0 ||
    (d.linked_controls?.length ?? 0) > 0
  );
}

/**
 * A stored register whose counters are DERIVED from its entries by the rules
 * `_serialize` uses (`app/routes/risk.py`), so no fixture can claim a count
 * its entries contradict:
 *
 * - `entries_without_tier`: entries with no tier;
 * - `entries_with_dropped_links`: a non-empty `dropped_links`, which includes
 *   an entry whose only drop is its `source_id`;
 * - `entries_unlinked_after_drops`: a dropped technique or control AND no
 *   technique or control link left;
 * - `entries_links_not_recorded`: `dropped_links` NULL (rows from before
 *   migration 0048);
 * - `dropped_citations`: every dropped value, or null when no entry carries a
 *   record (`_dropped_citations`).
 *
 * `over` carries only the fields that are not derived from the entries.
 */
function stored(
  entries: RiskEntry[],
  over: Partial<RiskRegister> = {},
): RiskRegister {
  const recorded = entries.filter((e) => e.dropped_links !== null);
  const values = recorded.reduce(
    (n, e) =>
      n +
      Object.values(e.dropped_links ?? {}).reduce((m, v) => m + v.length, 0),
    0,
  );
  return register({
    entries,
    entries_total: entries.length,
    entries_without_tier: entries.filter((e) => e.tier === null).length,
    entries_with_dropped_links: entries.filter(droppedAny).length,
    entries_unlinked_after_drops: entries.filter(
      (e) =>
        droppedAny(e) &&
        droppedALink(e) &&
        (e.linked_techniques ?? []).length === 0 &&
        (e.linked_controls ?? []).length === 0,
    ).length,
    entries_links_not_recorded: entries.length - recorded.length,
    dropped_citations: recorded.length === 0 ? null : values,
    ...over,
  });
}

/** `generate`: an entry that lost a technique and kept one. */
function keptLink(id: string): RiskEntry {
  return rated(id, {
    linked_techniques: ["T1078"],
    dropped_links: { linked_techniques: ["T9999"] },
  });
}

/** `generate`: an entry whose only proposed technique was dropped. */
function lostAllLinks(id: string): RiskEntry {
  return rated(id, { dropped_links: { linked_techniques: ["T9999"] } });
}

/**
 * `generate`: an entry whose only drop is its `source_id` and which never had
 * a technique or control link. It is in `entries_with_dropped_links`, it is
 * NOT in `entries_unlinked_after_drops`, and it shows no linkage.
 */
function sourceOnly(id: string): RiskEntry {
  return rated(id, {
    source_id: null,
    dropped_links: { source_id: ["T0000"] },
  });
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

  async function show(reg: RiskRegister): Promise<void> {
    fetchRiskRegisterLatest.mockResolvedValue(reg);
    await loaded();
  }

  async function textOf(testId: string, reg: RiskRegister): Promise<string> {
    await show(reg);
    return (await screen.findByTestId(testId)).textContent ?? "";
  }

  // `generate`, on a draft: the model left likelihood and impact unset.
  it("one unrated entry of one", async () => {
    const t = await textOf(
      "risk-entries-without-tier",
      stored([entry({ id: "e0" })]),
    );
    expect(t).toContain("1 of 1 entry has no likelihood, impact or tier");
    expect(t).toContain("so it is missing from the matrix");
  });

  it("two unrated entries of three", async () => {
    const t = await textOf(
      "risk-entries-without-tier",
      stored([entry({ id: "e0" }), entry({ id: "e1" }), rated("e2")]),
    );
    expect(t).toContain("2 of 3 entries have no likelihood, impact or tier");
    expect(t).toContain("so they are missing from the matrix");
  });

  // `_run_risk_synthesize_batched` re-raises when EVERY batch fails, so a
  // stored register has 1 <= batches_failed < batches_total: "1 of 1" cannot
  // be stored and is not built here.
  it("one synthesis batch of two failed", async () => {
    const t = await textOf(
      "risk-batches-failed",
      stored([rated("e0")], { batches_total: 2, batches_failed: 1 }),
    );
    expect(t).toContain("1 of 2 synthesis batches failed");
    expect(t).toContain("the entries that batch would have produced");
    expect(t).not.toContain("those batches");
  });

  it("two synthesis batches of three failed", async () => {
    const t = await textOf(
      "risk-batches-failed",
      stored([rated("e0")], { batches_total: 3, batches_failed: 2 }),
    );
    expect(t).toContain("2 of 3 synthesis batches failed");
    expect(t).toContain("the entries those batches would have produced");
  });

  // A RATCHET, not a reachable state: `generate` records `entries_intended`
  // as the same tally it stores, so no current writer produces a register
  // that intended more rows than it stored. Built directly so the wording the
  // banner would show is pinned all the same.
  it("entries lost before storage: one stored of two intended", async () => {
    const t = await textOf(
      "risk-entries-lost",
      stored([rated("e0")], { entries_intended: 2 }),
    );
    expect(t).toContain("1 of 2 entries did not reach storage");
    expect(t).toContain("describes the 1 stored, not the 2 the run intended");
  });

  it("entries lost before storage: two stored of three intended", async () => {
    const t = await textOf(
      "risk-entries-lost",
      stored([rated("e0"), rated("e1")], { entries_intended: 3 }),
    );
    expect(t).toContain("1 of 3 entries did not reach storage");
    expect(t).toContain("describes the 2 stored, not the 3 the run intended");
  });

  it("one entry of two kept none of its links", async () => {
    const t = await textOf(
      "risk-entries-unlinked-after-drops",
      stored([lostAllLinks("e0"), rated("e1")]),
    );
    expect(t).toContain(
      "1 of 2 entries proposed ATT&CK or control links and kept none",
    );
    expect(t).toContain("so it shows no linkage at all");
    expect(t).toContain("sees that row as unlinked");
    expect(t).not.toContain("so they show");
  });

  it("two entries of three kept none of their links", async () => {
    const t = await textOf(
      "risk-entries-unlinked-after-drops",
      stored([lostAllLinks("e0"), lostAllLinks("e1"), rated("e2")]),
    );
    expect(t).toContain(
      "2 of 3 entries proposed ATT&CK or control links and kept none",
    );
    expect(t).toContain("so they show no linkage at all");
    expect(t).toContain("sees those rows as unlinked");
  });

  it("one entry of two lost a value and still shows linkage", async () => {
    const t = await textOf(
      "risk-entries-with-dropped-links",
      stored([keptLink("e0"), rated("e1")]),
    );
    expect(t).toContain(
      "1 of 2 entries lost at least one value the model sent",
    );
    expect(t).toContain("the rest of it still resolved, so it shows linkage");
    expect(t).toContain("The values are on the entry");
  });

  // Three entries lost a value and one of them kept no link at all: the
  // banner counts the TWO that still show linkage.
  it("counts only the entries that still show linkage", async () => {
    const t = await textOf(
      "risk-entries-with-dropped-links",
      stored([keptLink("e0"), keptLink("e1"), lostAllLinks("e2"), rated("e3")]),
    );
    expect(t).toContain(
      "2 of 4 entries lost at least one value the model sent",
    );
    expect(t).toContain(
      "the rest of each still resolved, so they show linkage",
    );
    expect(t).not.toContain("3 of 4");
  });

  // Review round 2: an entry whose only drop is its `source_id` and which
  // has no link is in `entries_with_dropped_links` and NOT in the unlinked
  // count, so "with dropped minus unlinked" counted it as showing linkage.
  it("does not count a source-only drop on an entry with no link", async () => {
    const t = await textOf(
      "risk-entries-with-dropped-links",
      stored([sourceOnly("e0"), keptLink("e1")]),
    );
    expect(t).toContain(
      "1 of 2 entries lost at least one value the model sent",
    );
    expect(t).toContain("so it shows linkage");
    expect(t).not.toContain("2 of 2");
  });

  it("says nothing about linkage when the only drop is a source on an unlinked entry", async () => {
    await show(stored([sourceOnly("e0"), rated("e1")]));
    expect(
      await screen.findByTestId("risk-citations-dropped"),
    ).toHaveTextContent("1 citation value was discarded");
    expect(screen.queryByTestId("risk-entries-with-dropped-links")).toBeNull();
  });

  // Rows written before migration 0048 carry `dropped_links` NULL
  // (`seed_demo.py` builds its entries that way). One register is written by
  // one generate, so either every entry predates the recording or none does.
  it("one entry predating link recording", async () => {
    const t = await textOf(
      "risk-entries-links-not-recorded",
      stored([rated("e0", { dropped_links: null })]),
    );
    expect(t).toContain("1 of 1 entry predates link recording");
    expect(t).toContain("proposed linkage for it.");
    expect(t).not.toContain("for them");
  });

  it("three entries predating link recording", async () => {
    const t = await textOf(
      "risk-entries-links-not-recorded",
      stored([
        rated("e0", { dropped_links: null }),
        rated("e1", { dropped_links: null }),
        rated("e2", { dropped_links: null }),
      ]),
    );
    expect(t).toContain("3 of 3 entries predate link recording");
    expect(t).toContain("proposed linkage for them.");
  });

  // `generate`, one entry, nothing dropped.
  it("citations across a one-entry register", async () => {
    const t = await textOf("risk-citations-dropped", stored([rated("e0")]));
    expect(t).toContain("No citation values were discarded");
    expect(t).toContain("across the 1 entry.");
    expect(t).not.toContain("1 entries");
  });
});
