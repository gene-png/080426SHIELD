import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as attackClient from "@/lib/attack/client";
import type {
  AttackAssessment,
  AttackCatalog,
  AttackCoverageRow,
  AttackHeatmap,
} from "@/lib/attack/types";

import type * as React from "react";

import { AttackWorkspace } from "./AttackWorkspace";

/**
 * #554 R3, the #808 review's web finding 4: when a computed status moved between
 * the review panel loading and the click, the API refuses the stale pair
 * (`computed_status_changed`). The panel re-reads itself and says so, instead
 * of telling the consultant to find a reload control (CLAUDE.md: an imperative
 * names a control that exists). Copy pending the advisor.
 */

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

function row(computed: "covered" | "partial"): AttackCoverageRow {
  return {
    id: "row-1",
    assessment_id: "assess-1",
    technique_code: "T1003.001",
    status: "gap",
    reason_code: null,
    narrative: null,
    notes: null,
    evidence_artifact_id: null,
    answered_by: null,
    answered_at: null,
    computed_status: computed,
    capabilities: {
      detect: "in_place",
      prevent: computed === "covered" ? "in_place" : "not_in_place",
      respond: "in_place",
      line: "",
      awaiting_review: false,
      cannot_be_prevented: false,
    },
    in_review_queue: true,
    reviewed_status: null,
  };
}

function draft(computed: "covered" | "partial"): AttackAssessment {
  return {
    id: "assess-1",
    service_id: "svc-808",
    status: "draft",
    version: 1,
    coverage: [row(computed)],
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
});

describe("AttackWorkspace, a review whose computed status moved (#554 R3)", () => {
  it("re-reads the panel and says so, instead of naming a reload control", async () => {
    vi.mocked(attackClient.fetchLatestAssessment)
      .mockResolvedValueOnce(draft("covered"))
      .mockResolvedValueOnce(draft("partial"));
    const ProxyError = attackClient.AttackProxyError as unknown as new (
      m: string,
    ) => Error;
    vi.mocked(attackClient.reviewComputedStatuses).mockRejectedValueOnce(
      Object.assign(new ProxyError("ATT&CK proxy 409"), {
        status: 409,
        payload: {
          error: {
            code: 409,
            reason: "computed_status_changed",
            message: "ignored by the panel",
            codes: ["T1003.001"],
          },
        },
      }),
    );
    render(<AttackWorkspace serviceId="svc-808" serviceTitle="ATT&CK" />);

    const panel = await screen.findByTestId("attack-computed-review");
    expect(within(panel).getByText("Covered")).toBeInTheDocument();
    fireEvent.click(
      within(panel).getByRole("button", { name: "Mark 1 as reviewed" }),
    );

    expect(
      await screen.findByText(
        "The computed status of some techniques changed after the panel loaded (T1003.001). The panel has been refreshed; review again.",
      ),
    ).toBeInTheDocument();
    expect(attackClient.reviewComputedStatuses).toHaveBeenCalledWith(
      "assess-1",
      [{ code: "T1003.001", computed_status: "covered" }],
    );
    // The panel now shows what is true: Partial.
    const refreshed = screen.getByTestId("attack-computed-review");
    expect(within(refreshed).getByText("Partial")).toBeInTheDocument();
    expect(within(refreshed).queryByText("Covered")).toBeNull();
  });
});
