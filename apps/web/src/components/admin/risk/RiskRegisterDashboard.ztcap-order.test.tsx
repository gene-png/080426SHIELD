import "@testing-library/jest-dom/vitest";

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as riskClient from "@/lib/risk/client";
import type { RiskEntry, RiskGate, RiskRegister } from "@/lib/risk/types";

import { RiskRegisterDashboard } from "./RiskRegisterDashboard";

/**
 * #944, the advisor's ruling on #736 comment 6069566861, option 1: the DoD cap
 * note renders immediately after the Zero Trust target line, so #861's target
 * line and #915's note read as one baseline rather than two. No new copy, only
 * order. Both sentences are copied from their approved copy (#861's target
 * line; S3 at #736 comment 6049667540), never built from the code. Fixtures
 * copied from the #915 suite. Two target shapes: a CSF and a DoD Zero Trust
 * engagement, and a CISA and a DoD one, where the note must follow the
 * DoD line (the cap is DoD's), not merely the first Zero Trust line.
 *
 * Adjacency is read in DOCUMENT ORDER over the rendered text, which is the
 * order a reader and a screen reader meet it: the text that follows the Zero
 * Trust target line must be the cap note.
 */

const ZT_LINE =
  "Zero Trust findings are measured against target stage 3, the engagement target when this register was generated.";
const PLURAL =
  "In the DoD Zero Trust assessment, 15 capabilities have no DoD Advanced activities, so their target is Target (2): each is a finding only below Target. The Zero Trust deliverable names them.";

const CISA_LINE =
  "Zero Trust (CISA ZTMM 2.0) findings are measured against target stage 4, the engagement target when this register was generated.";
const DOD_LINE =
  "Zero Trust (DoD ZT Reference Architecture) findings are measured against target stage 3, the engagement target when this register was generated.";
const CISA_AND_DOD = [
  {
    kind: "zt",
    framework: "cisa_ztmm_2_0",
    target: 4,
    source: "client",
    origin: "live_at_generate",
  },
  {
    kind: "zt",
    framework: "dod_ztra",
    target: 3,
    source: "client",
    origin: "live_at_generate",
  },
];

/** Every non-blank text node under `root`, trimmed, in document order. */
function textsInOrder(root: HTMLElement): string[] {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const out: string[] = [];
  for (let n = walker.nextNode(); n !== null; n = walker.nextNode()) {
    const t = (n.textContent ?? "").trim();
    if (t !== "") out.push(t);
  }
  return out;
}

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

describe("RiskRegisterDashboard puts the DoD cap note after the Zero Trust target line (#944)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getActiveClientId.mockResolvedValue("c1");
    getClientName.mockResolvedValue("Client");
    fetchRiskGate.mockResolvedValue(gate());
  });

  it("renders the cap note immediately after the Zero Trust target line", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(
      register({
        targets: [
          {
            kind: "csf",
            framework: null,
            target: 3,
            source: "client",
            origin: "live_at_generate",
          },
          {
            kind: "zt",
            framework: "dod_ztra",
            target: 3,
            source: "client",
            origin: "live_at_generate",
          },
        ],
        targets_recorded: true,
        zt_capped_target_note: PLURAL,
      }),
    );
    await loaded();
    // The positive state first: both sentences are on the page, once each.
    const texts = textsInOrder(document.body);
    expect(texts.filter((t) => t === ZT_LINE)).toHaveLength(1);
    expect(texts.filter((t) => t === PLURAL)).toHaveLength(1);
    // Then the order: the cap note is the very next text.
    const at = texts.indexOf(ZT_LINE);
    expect(texts.slice(at + 1, at + 2)).toEqual([PLURAL]);
  });

  it("with CISA and DoD targets, renders the cap note immediately after the DoD line", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(
      register({
        targets: CISA_AND_DOD,
        targets_recorded: true,
        zt_capped_target_note: PLURAL,
      }),
    );
    await loaded();
    // The positive state first: both Zero Trust lines and the note, once each.
    const texts = textsInOrder(document.body);
    expect(texts.filter((t) => t === CISA_LINE)).toHaveLength(1);
    expect(texts.filter((t) => t === DOD_LINE)).toHaveLength(1);
    expect(texts.filter((t) => t === PLURAL)).toHaveLength(1);
    // Then the order: the cap note is the very next text after the DoD line.
    const at = texts.indexOf(DOD_LINE);
    expect(texts.slice(at + 1, at + 2)).toEqual([PLURAL]);
  });
});
