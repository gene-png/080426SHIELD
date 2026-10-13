import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import * as attackClient from "@/lib/attack/client";
import type {
  AttackAssessment,
  AttackCatalog,
  AttackHeatmap,
} from "@/lib/attack/types";
import { REVISION_COPY } from "@/lib/revisions/copy";

import type * as React from "react";

import { AttackWorkspace } from "./AttackWorkspace";

/**
 * #1120: "Start a revision" through the ATT&CK workspace, with the real button
 * and banner and the client mocked: the mount, the API's typed refusal
 * reaching the dialog through `describeError`, the swap to the draft (with
 * V4, the retired codes not copied), and the re-read after a draft_open
 * refusal. ATT&CK has no submitted state.
 */
vi.mock("@/lib/attack/client", () => ({
  AttackProxyError: class AttackProxyError extends Error {
    constructor(
      public readonly status: number,
      public readonly payload: unknown,
    ) {
      super(`ATT&CK proxy ${status}`);
    }
  },
  fetchCatalog: vi.fn(),
  fetchHeatmap: vi.fn(),
  fetchLatestAssessment: vi.fn(),
  fetchLatestDeliverable: vi.fn(),
  createAssessment: vi.fn(),
  approveAssessment: vi.fn(),
  discardAssessment: vi.fn(),
  startRevision: vi.fn(),
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
vi.mock("./AttackTechniquePanel", () => ({ AttackTechniquePanel: () => null }));
vi.mock("./AttackScenarioPanel", () => ({ AttackScenarioPanel: () => null }));
vi.mock("./AttackAiInputsPanel", () => ({ AttackAiInputsPanel: () => null }));
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

function record(
  id: string,
  version: number,
  status: string,
  revision: (typeof REVISION & { retired_codes: string[] }) | null = null,
): AttackAssessment {
  return {
    id,
    status,
    version,
    coverage: [],
    documents_stale: false,
    revision,
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

const REVISION = {
  from_version: 1,
  started_by_name: "Ann Consultant",
  started_at: "2026-10-13T10:00:00Z",
  reason: "Correct a score",
  rules_changed: false,
  retired_codes: [] as string[],
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

const V1 = record("attack-v1", 1, "approved");

beforeEach(() => {
  vi.mocked(attackClient.fetchCatalog).mockResolvedValue({
    techniques: [],
    coverage_definitions: [],
    reason_codes: [],
  } as unknown as AttackCatalog);
  vi.mocked(attackClient.fetchHeatmap).mockResolvedValue({
    by_tactic: [],
  } as unknown as AttackHeatmap);
  vi.mocked(attackClient.fetchLatestAssessment).mockReset();
  vi.mocked(attackClient.fetchLatestAssessment).mockResolvedValue(V1);
  vi.mocked(attackClient.fetchLatestDeliverable).mockResolvedValue(null);
  vi.mocked(attackClient.startRevision).mockReset();
});

function renderWorkspace(): void {
  render(<AttackWorkspace serviceId="svc-1" serviceTitle="Atlas ATT&CK" />);
}

describe("AttackWorkspace: Start a revision", () => {
  it("swaps to the draft and shows V5 and V4", async () => {
    vi.mocked(attackClient.startRevision).mockResolvedValue(
      record("attack-v2", 2, "draft", {
        ...REVISION,
        retired_codes: ["T1001", "T1002"],
      }),
    );
    renderWorkspace();

    await startRevisionThroughTheDialog();

    expect(await screen.findByText("Draft v2")).toBeInTheDocument();
    expect(
      screen.getByText(
        /^Revision of version 1, started by Ann Consultant on .+: Correct a score\.$/,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "This revision uses the current ATT&CK catalog. 2 techniques from version 1 are no longer in it and were not copied: T1001, T1002.",
      ),
    ).toBeInTheDocument();
    expect(attackClient.startRevision).toHaveBeenCalledWith(
      "svc-1",
      "attack-v1",
      "Correct a score",
    );
  });

  it("shows a typed 409 refusal in the dialog, in the API's words", async () => {
    vi.mocked(attackClient.startRevision).mockRejectedValue(
      new attackClient.AttackProxyError(409, {
        error: { reason: "not_latest", message: V12 },
      }),
    );
    renderWorkspace();

    await startRevisionThroughTheDialog();

    expect(await dialogAlert()).toHaveTextContent(V12);
    expect(screen.getByText("Approved v1")).toBeInTheDocument();
    expect(attackClient.fetchLatestAssessment).toHaveBeenCalledTimes(1);
  });

  it("after a draft_open refusal, shows the draft beneath the dialog's message", async () => {
    vi.mocked(attackClient.startRevision).mockRejectedValue(
      new attackClient.AttackProxyError(409, {
        error: { reason: "draft_open", message: V6 },
      }),
    );
    vi.mocked(attackClient.fetchLatestAssessment)
      .mockResolvedValueOnce(V1)
      .mockResolvedValue(record("attack-v2", 2, "draft"));
    renderWorkspace();

    await startRevisionThroughTheDialog();

    expect(await screen.findByText("Draft v2")).toBeInTheDocument();
    expect(await dialogAlert()).toHaveTextContent(V6);
    expect(
      screen.queryByRole("button", { name: REVISION_COPY.V1 }),
    ).not.toBeInTheDocument();
  });

  it("offers no revision on a draft record", async () => {
    vi.mocked(attackClient.fetchLatestAssessment).mockResolvedValue(
      record("attack-v1", 1, "draft"),
    );
    renderWorkspace();
    expect(await screen.findByText("Draft v1")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: REVISION_COPY.V1 }),
    ).not.toBeInTheDocument();
  });
});
