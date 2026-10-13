import "@testing-library/jest-dom/vitest";

import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import * as csfClient from "@/lib/csf/client";
import { REVISION_COPY } from "@/lib/revisions/copy";
import type {
  CsfAssessment,
  CsfCatalog,
  CsfDimensionScore,
  CsfScoreSummary,
  EnterpriseProfile,
  GapAnalysis,
} from "@/lib/csf/types";

import type * as React from "react";

import { CsfWorkspace } from "./CsfWorkspace";

/**
 * #1120: "Start a revision" through the CSF workspace, with the real button,
 * banner, Playbook panel and dimension editor, and the client mocked. Pins the
 * wiring the isolated component tests cannot: the mount, the API's typed
 * refusal reaching the dialog through `describeError`, the swap to the draft,
 * and the Working Profile editor following the swap (it loads rows by service,
 * so without a remount it PATCHes the approved record's rows).
 */
vi.mock("@/lib/csf/client", () => ({
  CsfProxyError: class CsfProxyError extends Error {
    constructor(
      public readonly status: number,
      public readonly payload: unknown,
    ) {
      super(`CSF proxy ${status}`);
    }
  },
  fetchCatalog: vi.fn(),
  fetchInterviewQuestionnaire: vi.fn(),
  fetchLatestAssessment: vi.fn(),
  fetchLatestDeliverable: vi.fn(),
  fetchScore: vi.fn(),
  fetchGapAnalysis: vi.fn(),
  createAssessment: vi.fn(),
  approveAssessment: vi.fn(),
  discardAssessment: vi.fn(),
  startRevision: vi.fn(),
  patchAnswer: vi.fn(),
  fetchEnterpriseProfile: vi.fn(),
  fetchProfile: vi.fn(),
  patchDimensionScore: vi.fn(),
  seedProfiles: vi.fn(),
  runCsfAi: vi.fn(),
  fetchCsfRun: vi.fn(),
  fetchCsfRunSummary: vi.fn(() =>
    Promise.resolve({ running: null, latest: null, last_completed: null }),
  ),
  exportPlaybook: vi.fn(),
}));
vi.mock("@/lib/stages/client", () => ({
  useServiceStages: () => ({ phase: "ready", stages: null }),
}));
vi.mock("./CsfScoreCard", () => ({ CsfScoreCard: () => null }));
vi.mock("./CsfGapList", () => ({ CsfGapList: () => null }));
vi.mock("./CsfDeliverableCard", () => ({ CsfDeliverableCard: () => null }));
vi.mock("./CsfQuestionnaire", () => ({ CsfQuestionnaire: () => null }));
vi.mock("./CsfGapActionEditor", () => ({ CsfGapActionEditor: () => null }));
vi.mock("@/components/admin/AiPreviewButton", () => ({
  AiPreviewButton: () => null,
}));
vi.mock("@/components/messages/MessageThread", () => ({
  MessageThread: () => null,
}));
vi.mock("@/components/admin/StaleDocsNudge", () => ({
  StaleDocsNudge: () => null,
}));

const ENTERPRISE = {
  tiers_in_use: ["high"],
  subcategories: [
    {
      subcategory_code: "GV.OC-01",
      name: "GV.OC-01 outcome",
      function: "GV",
      tier_levels: { high: 2 },
      enterprise_level: 2,
      rollup_rule: 1,
      target_level: 3,
      gap: false,
      priority: null,
    },
  ],
} as EnterpriseProfile;

const REVISION = {
  from_version: 1,
  started_by_name: "Ann Consultant",
  started_at: "2026-10-13T10:00:00Z",
  reason: "Correct a score",
  rules_changed: false,
  retired_codes: [],
};

function record(
  id: string,
  version: number,
  status: string,
  revision: typeof REVISION | null = null,
): CsfAssessment {
  return {
    id,
    status,
    version,
    answers: [],
    client_target_tier: 3,
    documents_stale: false,
    revision,
    ai_source: {
      state: "none",
      sentence: "No AI suggestions were used in this assessment.",
      live_runs: 0,
      fixture_runs: 0,
    },
  } as unknown as CsfAssessment;
}

const V1 = record("assess-v1", 1, "approved");
const V2 = record("assess-v2", 2, "draft", REVISION);

/** The record whose Working Profile rows `fetchProfile` serves. */
let current = "v1";

function row(id: string): CsfDimensionScore {
  return {
    id,
    tier: "high",
    subcategory_code: "GV.OC-01",
    governance: 1,
    policy: 1,
    implementation: 1,
    monitoring: 1,
    improvement: 1,
    in_scope: true,
    rationale: null,
    what_we_found: null,
    has_evidence: true,
    target_level: null,
    locked: false,
    total: 5,
    level: 2,
    evidence_capped: false,
  };
}

beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function showModal(): void {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function close(): void {
    this.open = false;
    this.dispatchEvent(new Event("close"));
  };
});

beforeEach(() => {
  current = "v1";
  vi.mocked(csfClient.fetchCatalog).mockResolvedValue(
    {} as unknown as CsfCatalog,
  );
  vi.mocked(csfClient.fetchInterviewQuestionnaire).mockResolvedValue(null);
  vi.mocked(csfClient.fetchLatestAssessment).mockReset();
  vi.mocked(csfClient.fetchLatestAssessment).mockResolvedValue(V1);
  vi.mocked(csfClient.fetchLatestDeliverable).mockResolvedValue(null);
  vi.mocked(csfClient.fetchScore).mockResolvedValue(
    {} as unknown as CsfScoreSummary,
  );
  vi.mocked(csfClient.fetchGapAnalysis).mockResolvedValue(
    {} as unknown as GapAnalysis,
  );
  vi.mocked(csfClient.fetchEnterpriseProfile).mockResolvedValue(ENTERPRISE);
  vi.mocked(csfClient.fetchProfile).mockReset();
  vi.mocked(csfClient.fetchProfile).mockImplementation(async (_s, tier) => ({
    tier,
    rows: [row(`row-${current}`)],
  }));
  vi.mocked(csfClient.patchDimensionScore).mockReset();
  vi.mocked(csfClient.patchDimensionScore).mockImplementation(
    async (id, patch) => ({ ...row(id), ...patch }),
  );
  vi.mocked(csfClient.startRevision).mockReset();
});

async function startRevisionThroughTheDialog(): Promise<void> {
  fireEvent.click(
    await screen.findByRole("button", { name: REVISION_COPY.V1 }),
  );
  fireEvent.change(screen.getByLabelText(REVISION_COPY.V2b_LABEL), {
    target: { value: "Correct a score" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: REVISION_COPY.V2c_CONFIRM }),
  );
}

/** The dialog's own alert: the page carries unrelated ones (AI status). */
async function dialogAlert(): Promise<HTMLElement> {
  const body = (await screen.findByText(REVISION_COPY.V2b_HINT)).parentElement;
  if (!body) throw new Error("the revision dialog has no body");
  return within(body).findByRole("alert");
}

describe("CsfWorkspace: Start a revision", () => {
  it("swaps to the draft, shows V5, and the editor then PATCHes the draft's row", async () => {
    vi.mocked(csfClient.startRevision).mockImplementation(async () => {
      current = "v2";
      return V2;
    });
    render(<CsfWorkspace serviceId="svc-1" serviceTitle="Acme" />);
    // The approved record's editor is loaded first.
    await waitFor(() =>
      expect(csfClient.fetchProfile).toHaveBeenCalledTimes(1),
    );

    await startRevisionThroughTheDialog();

    expect(await screen.findByText("Draft v2")).toBeInTheDocument();
    expect(
      screen.getByText(
        /^Revision of version 1, started by Ann Consultant on .+: Correct a score\.$/,
      ),
    ).toBeInTheDocument();
    expect(csfClient.startRevision).toHaveBeenCalledWith(
      "svc-1",
      "assess-v1",
      "Correct a score",
    );

    const governance = await screen.findByRole("radiogroup", {
      name: "Governance",
    });
    const two = governance.querySelectorAll("button")[2];
    await waitFor(() => expect(two).toBeEnabled());
    fireEvent.click(two);
    await waitFor(() =>
      expect(csfClient.patchDimensionScore).toHaveBeenCalledTimes(1),
    );
    expect(csfClient.patchDimensionScore).toHaveBeenCalledWith("row-v2", {
      governance: 2,
    });
  });

  it("shows a typed 409 refusal in the dialog, in the API's words", async () => {
    vi.mocked(csfClient.startRevision).mockRejectedValue(
      new csfClient.CsfProxyError(409, {
        error: {
          reason: "not_latest",
          message:
            "Version 3 is newer than version 1. Only the newest version can be revised.",
        },
      }),
    );
    render(<CsfWorkspace serviceId="svc-1" serviceTitle="Acme" />);

    await startRevisionThroughTheDialog();

    expect(await dialogAlert()).toHaveTextContent(
      "Version 3 is newer than version 1. Only the newest version can be revised.",
    );
    expect(screen.getByText("Approved v1")).toBeInTheDocument();
    expect(csfClient.fetchLatestAssessment).toHaveBeenCalledTimes(1);
  });

  it("after a draft_open refusal, shows the draft beneath the dialog's message", async () => {
    const v6 =
      "Version 2 is open as a draft. Approve it, or discard it, before starting another revision.";
    vi.mocked(csfClient.startRevision).mockRejectedValue(
      new csfClient.CsfProxyError(409, {
        error: { reason: "draft_open", message: v6 },
      }),
    );
    vi.mocked(csfClient.fetchLatestAssessment)
      .mockResolvedValueOnce(V1)
      .mockResolvedValue(record("assess-v2", 2, "draft"));
    render(<CsfWorkspace serviceId="svc-1" serviceTitle="Acme" />);

    await startRevisionThroughTheDialog();

    expect(await screen.findByText("Draft v2")).toBeInTheDocument();
    expect(await dialogAlert()).toHaveTextContent(v6);
    expect(
      screen.queryByRole("button", { name: REVISION_COPY.V1 }),
    ).not.toBeInTheDocument();
  });

  it.each(["draft", "submitted"])(
    "offers no revision on a %s record",
    async (status) => {
      vi.mocked(csfClient.fetchLatestAssessment).mockResolvedValue(
        record("assess-v1", 1, status),
      );
      render(<CsfWorkspace serviceId="svc-1" serviceTitle="Acme" />);
      // Positive first: the page has rendered the record.
      expect(
        await screen.findByText(
          status === "draft" ? "Draft v1" : "Submitted v1",
        ),
      ).toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: REVISION_COPY.V1 }),
      ).not.toBeInTheDocument();
    },
  );
});
