import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import * as csfClient from "@/lib/csf/client";
import type {
  CsfAssessment,
  CsfCatalog,
  CsfScoreSummary,
  GapAnalysis,
} from "@/lib/csf/types";

import { CsfWorkspace } from "./CsfWorkspace";

// Deterministic + offline: the CSF client lib is fully mocked and every child
// that fetches on its own is stubbed, so the only requests in play are the
// workspace's own. Each test drives the exact resolution ordering the reqSeq
// stale-fetch guard exists to defend against.
vi.mock("@/lib/csf/client", () => ({
  CsfProxyError: class extends Error {},
  fetchCatalog: vi.fn(),
  fetchInterviewQuestionnaire: vi.fn(),
  fetchLatestAssessment: vi.fn(),
  fetchLatestDeliverable: vi.fn(),
  fetchScore: vi.fn(),
  fetchGapAnalysis: vi.fn(),
  createAssessment: vi.fn(),
  approveAssessment: vi.fn(),
  discardAssessment: vi.fn(),
  patchAnswer: vi.fn(),
}));

// Stub the children so no child effect fetches and the test stays focused on
// the workspace's own reqSeq logic.
vi.mock("./CsfScoreCard", () => ({ CsfScoreCard: () => null }));
vi.mock("./CsfPlaybookPanel", () => ({ CsfPlaybookPanel: () => null }));
vi.mock("./CsfGapList", () => ({ CsfGapList: () => null }));
vi.mock("./CsfDeliverableCard", () => ({ CsfDeliverableCard: () => null }));
vi.mock("./CsfQuestionnaire", () => ({ CsfQuestionnaire: () => null }));
vi.mock("@/components/messages/MessageThread", () => ({
  MessageThread: () => null,
}));
vi.mock("@/components/admin/StaleDocsNudge", () => ({
  StaleDocsNudge: () => null,
}));

const fetchCatalog = vi.mocked(csfClient.fetchCatalog);
const fetchInterviewQuestionnaire = vi.mocked(
  csfClient.fetchInterviewQuestionnaire,
);
const fetchLatestAssessment = vi.mocked(csfClient.fetchLatestAssessment);
const fetchScore = vi.mocked(csfClient.fetchScore);
const fetchGapAnalysis = vi.mocked(csfClient.fetchGapAnalysis);
const createAssessment = vi.mocked(csfClient.createAssessment);
const discardAssessment = vi.mocked(csfClient.discardAssessment);

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

const CATALOG = {} as unknown as CsfCatalog;
const SCORE = {} as unknown as CsfScoreSummary;
const GAP = {} as unknown as GapAnalysis;

function draft(): CsfAssessment {
  return {
    id: "assess-1",
    status: "draft",
    version: 1,
    answers: [],
    client_target_tier: 3,
    documents_stale: false,
  } as unknown as CsfAssessment;
}

// A draft with two answered rows (a maturity tier and a client note) plus one
// untouched row — the discard dialog must report "2 answers".
function draftWithAnswers(): CsfAssessment {
  return {
    id: "assess-2",
    status: "draft",
    version: 1,
    answers: [
      { id: "a1", maturity_tier: 3, notes: null, evidence_artifact_id: null },
      {
        id: "a2",
        maturity_tier: null,
        notes: "client note",
        evidence_artifact_id: null,
      },
      {
        id: "a3",
        maturity_tier: null,
        notes: null,
        evidence_artifact_id: null,
      },
    ],
    client_target_tier: 3,
    documents_stale: false,
  } as unknown as CsfAssessment;
}

// jsdom does not implement <dialog>.showModal()/.close(); the shared
// DiscardDraftButton opens the design-system Modal, so stub them here too.
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function showModal(): void {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function close(): void {
    this.open = false;
    this.dispatchEvent(new Event("close"));
  };
});

describe("CsfWorkspace reqSeq stale-fetch guard", () => {
  it("discards the slow mount assessment GET after a newer create", async () => {
    fetchCatalog.mockResolvedValue(CATALOG);
    fetchInterviewQuestionnaire.mockResolvedValue(null);
    // The mount's latest-assessment GET stays in flight while the user starts a
    // fresh assessment — it will resolve LAST with the pre-create null.
    const latest = deferred<CsfAssessment | null>();
    fetchLatestAssessment.mockReturnValue(latest.promise);
    createAssessment.mockResolvedValue(draft());
    fetchScore.mockResolvedValue(SCORE);
    fetchGapAnalysis.mockResolvedValue(GAP);

    render(<CsfWorkspace serviceId="svc-1" serviceTitle="Atlas CSF" />);

    // Catalog resolved → the empty-state Start button is live while the
    // assessment GET is still pending.
    const start = await screen.findByRole("button", {
      name: "Start assessment",
    });

    await act(async () => {
      fireEvent.click(start);
    });
    // The create settles first: the fresh draft is on screen.
    await screen.findByText("Draft v1");

    // The slow mount GET now resolves with the stale pre-create null. Without
    // the guard this setAssessment(null) would clobber the created draft back
    // to the empty state.
    await act(async () => {
      latest.resolve(null);
      await latest.promise;
    });

    expect(screen.getByText("Draft v1")).toBeInTheDocument();
    expect(screen.queryByText("No CSF assessment yet")).not.toBeInTheDocument();
  });

  it("surfaces a failed catalog load to the error state (fail loudly)", async () => {
    fetchCatalog.mockRejectedValue(new Error("boom-catalog"));
    fetchInterviewQuestionnaire.mockResolvedValue(null);
    fetchLatestAssessment.mockResolvedValue(null);

    render(<CsfWorkspace serviceId="svc-err" serviceTitle="Atlas CSF" />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("boom-catalog");
  });
});

describe("CsfWorkspace discard affordance", () => {
  it("warns with the client-entered answer count in the discard dialog", async () => {
    fetchCatalog.mockResolvedValue(CATALOG);
    fetchInterviewQuestionnaire.mockResolvedValue(null);
    fetchLatestAssessment.mockResolvedValue(draftWithAnswers());
    fetchScore.mockResolvedValue(SCORE);
    fetchGapAnalysis.mockResolvedValue(GAP);

    const { container } = render(
      <CsfWorkspace serviceId="svc-1" serviceTitle="Atlas CSF" />,
    );

    // Draft is loaded → the Discard draft affordance is live beside Approve.
    await screen.findByText("Draft v1");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Discard draft" }));
    });

    const dialog = container.querySelector("dialog") as HTMLDialogElement;
    expect(dialog.open).toBe(true);
    expect(
      within(dialog).getByText(
        "2 answers, including client-entered data, will be discarded.",
      ),
    ).toBeInTheDocument();
  });

  it("confirming the discard clears the workspace back to the empty state", async () => {
    fetchCatalog.mockResolvedValue(CATALOG);
    fetchInterviewQuestionnaire.mockResolvedValue(null);
    // Mount loads the draft; the post-discard refetch resolves null (GET
    // latest 404 → empty state, Start live again).
    fetchLatestAssessment
      .mockResolvedValueOnce(draftWithAnswers())
      .mockResolvedValue(null);
    fetchScore.mockResolvedValue(SCORE);
    fetchGapAnalysis.mockResolvedValue(GAP);
    discardAssessment.mockResolvedValue({
      ...draftWithAnswers(),
      status: "discarded",
    } as unknown as CsfAssessment);

    const { container } = render(
      <CsfWorkspace serviceId="svc-1" serviceTitle="Atlas CSF" />,
    );

    await screen.findByText("Draft v1");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Discard draft" }));
    });
    const dialog = container.querySelector("dialog") as HTMLDialogElement;
    await act(async () => {
      fireEvent.click(
        within(dialog).getByRole("button", { name: "Yes, discard" }),
      );
    });

    // The workspace called discard for the loaded draft, then the guarded
    // refetch returned null and the empty state is shown again — the draft (and
    // with it the Discard affordance) is gone, Start is live.
    expect(discardAssessment).toHaveBeenCalledWith("assess-2");
    expect(
      await screen.findByText("No CSF assessment yet"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Discard draft" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Start assessment" }),
    ).toBeInTheDocument();
  });
});
