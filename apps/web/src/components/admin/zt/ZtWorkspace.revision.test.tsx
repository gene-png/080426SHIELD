import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { REVISION_COPY } from "@/lib/revisions/copy";
import * as ztClient from "@/lib/zt/client";
import type {
  GapAnalysis,
  ZtAssessment,
  ZtCatalog,
  ZtScoreSummary,
} from "@/lib/zt/types";

import type * as React from "react";

import { ZtWorkspace } from "./ZtWorkspace";

/**
 * #1120: "Start a revision" through the ZT workspace, with the real button and
 * banner and the client mocked: the mount, the API's typed refusal reaching
 * the dialog through `describeError`, the swap to the draft, and the re-read
 * after a draft_open refusal.
 */
vi.mock("@/lib/zt/client", () => ({
  ZtProxyError: class ZtProxyError extends Error {
    constructor(
      public readonly status: number,
      public readonly payload: unknown,
    ) {
      super(`ZT proxy ${status}`);
    }
  },
  fetchCatalog: vi.fn(),
  fetchLatestAssessment: vi.fn(),
  fetchLatestDeliverable: vi.fn(),
  fetchScore: vi.fn(),
  fetchGapAnalysis: vi.fn(),
  createAssessment: vi.fn(),
  approveAssessment: vi.fn(),
  discardAssessment: vi.fn(),
  startRevision: vi.fn(),
  patchAnswer: vi.fn(),
  runZtAi: vi.fn(),
  fetchZtRun: vi.fn(),
  fetchZtRunSummary: vi.fn(() =>
    Promise.resolve({ running: null, latest: null, last_completed: null }),
  ),
  finalizeZtDeliverable: vi.fn(),
  releaseZtDeliverable: vi.fn(),
}));
vi.mock("@/lib/stages/client", () => ({
  useServiceStages: () => ({ phase: "ready", stages: null }),
}));
vi.mock("./ZtScoreCard", () => ({ ZtScoreCard: () => null }));
vi.mock("./ZtGapList", () => ({ ZtGapList: () => null }));
vi.mock("./ZtRoadmapCard", () => ({ ZtRoadmapCard: () => null }));
vi.mock("./ZtQuestionnaire", () => ({ ZtQuestionnaire: () => null }));
vi.mock("./ZtDeliverableCard", () => ({ ZtDeliverableCard: () => null }));
vi.mock("@/components/messages/MessageThread", () => ({
  MessageThread: () => null,
}));
vi.mock("@/components/admin/StaleDocsNudge", () => ({
  StaleDocsNudge: () => null,
}));
vi.mock("@/components/admin/AiPreviewButton", () => ({
  AiPreviewButton: () => null,
}));
vi.mock("@/components/admin/RunAiGuard", () => ({
  RunAiGuard: (props: {
    onProceed: () => void;
    children: (p: { onClick: () => void }) => React.ReactNode;
  }) => props.children({ onClick: props.onProceed }),
}));

function record(
  id: string,
  version: number,
  status: string,
  revision: typeof REVISION | null = null,
): ZtAssessment {
  return {
    id,
    status,
    version,
    answers: [],
    client_target_stage: 3,
    documents_stale: false,
    revision,
    ai_source: {
      state: "none",
      sentence: "No AI suggestions were used in this assessment.",
      live_runs: 0,
      fixture_runs: 0,
    },
  } as unknown as ZtAssessment;
}

const REVISION = {
  from_version: 1,
  started_by_name: "Ann Consultant",
  started_at: "2026-10-13T10:00:00Z",
  reason: "Correct a score",
  rules_changed: false,
  retired_codes: [],
};

const V12 =
  "Version 3 is newer than version 1. Only the newest version can be revised.";
const V6 =
  "Version 2 is open as a draft. Approve it, or discard it, before starting another revision.";

beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function showModal(): void {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function close(): void {
    this.open = false;
    this.dispatchEvent(new Event("close"));
  };
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

/** The dialog's own alert: the page may carry unrelated ones. */
async function dialogAlert(): Promise<HTMLElement> {
  const body = (await screen.findByText(REVISION_COPY.V2b_HINT)).parentElement;
  if (!body) throw new Error("the revision dialog has no body");
  return within(body).findByRole("alert");
}

const V1 = record("zt-v1", 1, "approved");

beforeEach(() => {
  vi.mocked(ztClient.fetchCatalog).mockResolvedValue({
    pillars: [],
    stages: [],
  } as unknown as ZtCatalog);
  vi.mocked(ztClient.fetchLatestAssessment).mockReset();
  vi.mocked(ztClient.fetchLatestAssessment).mockResolvedValue(V1);
  vi.mocked(ztClient.fetchLatestDeliverable).mockResolvedValue(null);
  vi.mocked(ztClient.fetchScore).mockResolvedValue(
    {} as unknown as ZtScoreSummary,
  );
  vi.mocked(ztClient.fetchGapAnalysis).mockResolvedValue(
    {} as unknown as GapAnalysis,
  );
  vi.mocked(ztClient.startRevision).mockReset();
});

function renderWorkspace(): void {
  render(
    <ZtWorkspace
      serviceId="svc-1"
      framework="cisa_ztmm_2_0"
      serviceTitle="Atlas Zero Trust"
    />,
  );
}

describe("ZtWorkspace: Start a revision", () => {
  it("swaps to the draft and shows V5", async () => {
    vi.mocked(ztClient.startRevision).mockResolvedValue(
      record("zt-v2", 2, "draft", REVISION),
    );
    renderWorkspace();

    await startRevisionThroughTheDialog();

    expect(await screen.findByText("Draft v2")).toBeInTheDocument();
    expect(
      screen.getByText(
        /^Revision of version 1, started by Ann Consultant on .+: Correct a score\.$/,
      ),
    ).toBeInTheDocument();
    expect(ztClient.startRevision).toHaveBeenCalledWith(
      "svc-1",
      "zt-v1",
      "Correct a score",
    );
  });

  it("shows a typed 409 refusal in the dialog, in the API's words", async () => {
    vi.mocked(ztClient.startRevision).mockRejectedValue(
      new ztClient.ZtProxyError(409, {
        error: { reason: "not_latest", message: V12 },
      }),
    );
    renderWorkspace();

    await startRevisionThroughTheDialog();

    expect(await dialogAlert()).toHaveTextContent(V12);
    expect(screen.getByText("Approved v1")).toBeInTheDocument();
    expect(ztClient.fetchLatestAssessment).toHaveBeenCalledTimes(1);
  });

  it("after a draft_open refusal, shows the draft beneath the dialog's message", async () => {
    vi.mocked(ztClient.startRevision).mockRejectedValue(
      new ztClient.ZtProxyError(409, {
        error: { reason: "draft_open", message: V6 },
      }),
    );
    vi.mocked(ztClient.fetchLatestAssessment)
      .mockResolvedValueOnce(V1)
      .mockResolvedValue(record("zt-v2", 2, "draft"));
    renderWorkspace();

    await startRevisionThroughTheDialog();

    expect(await screen.findByText("Draft v2")).toBeInTheDocument();
    expect(await dialogAlert()).toHaveTextContent(V6);
    expect(
      screen.queryByRole("button", { name: REVISION_COPY.V1 }),
    ).not.toBeInTheDocument();
  });

  it("when the re-read after a draft_open refusal fails, says so and keeps v1", async () => {
    const draftOpen =
      "Version 2 is open as a draft. Approve it, or discard it, before starting another revision.";
    vi.mocked(ztClient.startRevision).mockRejectedValue(
      new ztClient.ZtProxyError(409, {
        error: { reason: "draft_open", message: draftOpen },
      }),
    );
    vi.mocked(ztClient.fetchLatestAssessment)
      .mockResolvedValueOnce(V1)
      .mockRejectedValue(
        new ztClient.ZtProxyError(503, {
          error: { message: "The service is unavailable right now." },
        }),
      );
    renderWorkspace();

    await startRevisionThroughTheDialog();

    expect(
      await screen.findByText("The service is unavailable right now."),
    ).toBeInTheDocument();
    expect(screen.getByText("Approved v1")).toBeInTheDocument();
    expect(await dialogAlert()).toHaveTextContent(draftOpen);
    expect(ztClient.fetchLatestAssessment).toHaveBeenCalledTimes(2);
  });

  it.each(["draft", "submitted"])(
    "offers no revision on a %s record",
    async (status) => {
      vi.mocked(ztClient.fetchLatestAssessment).mockResolvedValue(
        record("zt-v1", 1, status),
      );
      renderWorkspace();
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
