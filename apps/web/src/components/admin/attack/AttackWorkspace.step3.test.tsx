import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as attackClient from "@/lib/attack/client";
import type {
  AttackAssessment,
  AttackCatalog,
  AttackHeatmap,
} from "@/lib/attack/types";

import type * as React from "react";

import { AttackWorkspace } from "./AttackWorkspace";

/**
 * #1179, Gene's 2026-10-15 test-run item (11): step 3 adds "Review each item
 * with the client and confirm they agree before approving", keeping the
 * current text. Both sentences are literals typed here, never imported.
 */

const CURRENT =
  "Locks the coverage matrix so the deliverable is generated from a fixed set of scores. Approving does not release anything to the client — that is the last step.";
const GENE =
  "Review each item with the client and confirm they agree before approving.";

vi.mock("@/lib/attack/client", () => ({
  AttackProxyError: class extends Error {},
  fetchCatalog: vi.fn(),
  fetchHeatmap: vi.fn(),
  fetchLatestAssessment: vi.fn(),
  fetchLatestDeliverable: vi.fn(),
  createAssessment: vi.fn(),
  approveAssessment: vi.fn(),
  reviewComputedStatuses: vi.fn(),
  patchCoverage: vi.fn(),
  confirmCoverageCitations: vi.fn(),
  runAttackAi: vi.fn(),
  fetchAttackRun: vi.fn(),
  fetchAttackRunSummary: vi.fn(() =>
    Promise.resolve({ running: null, latest: null, last_completed: null }),
  ),
}));
vi.mock("./AttackDeliverableCard", () => ({
  AttackDeliverableCard: () => null,
}));
vi.mock("./AttackHeatmapCard", () => ({ AttackHeatmapCard: () => null }));
vi.mock("./AttackMatrix", () => ({ AttackMatrix: () => null }));
vi.mock("./AttackTechniquePanel", () => ({
  AttackTechniquePanel: () => null,
}));
vi.mock("./AttackAiInputsPanel", () => ({
  AttackAiInputsPanel: () => null,
}));
vi.mock("@/components/messages/MessageThread", () => ({
  MessageThread: () => null,
}));
vi.mock("@/components/admin/StaleDocsNudge", () => ({
  StaleDocsNudge: () => null,
}));
vi.mock("@/components/admin/RunAiGuard", () => ({
  RunAiGuard: (props: {
    onProceed: () => void;
    children: (p: { onClick: () => void }) => React.ReactNode;
  }) => props.children({ onClick: props.onProceed }),
}));
vi.mock("@/components/admin/AiPreviewButton", () => ({
  AiPreviewButton: () => null,
}));

function draft(): AttackAssessment {
  return {
    id: "assess-1",
    service_id: "svc-1179",
    status: "draft",
    version: 1,
    coverage: [],
    documents_stale: false,
    statuses_computed: true,
    ai_source: {
      state: "none",
      sentence: "No AI suggestions were used in this assessment.",
      live_runs: 0,
      fixture_runs: 0,
    },
    catalog_version: "19.2",
    catalog_current: true,
  } as unknown as AttackAssessment;
}

beforeEach(() => {
  vi.mocked(attackClient.fetchCatalog).mockResolvedValue({
    techniques: [],
    coverage_definitions: [],
    reason_codes: [],
  } as unknown as AttackCatalog);
  vi.mocked(attackClient.fetchHeatmap).mockResolvedValue({
    by_tactic: [],
  } as unknown as AttackHeatmap);
  vi.mocked(attackClient.fetchLatestDeliverable).mockResolvedValue(null);
  vi.mocked(attackClient.fetchLatestAssessment).mockResolvedValue(draft());
});

describe("AttackWorkspace, step 3 (#1179)", () => {
  it("asks the consultant to review each item with the client, after the current text", async () => {
    render(<AttackWorkspace serviceId="svc-1179" serviceTitle="ATT&CK" />);
    const heading = await screen.findByRole("heading", {
      name: "Step 3: Approve the assessment",
    });
    const description = heading.nextElementSibling;
    expect(description?.textContent).toBe(`${CURRENT} ${GENE}`);
  });
});
