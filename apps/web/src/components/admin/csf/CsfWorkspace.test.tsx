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

// ---------------------------------------------------------------------------
// #292 -- a failed supplementary fetch was swallowed, leaving `score`, `gap`
// and `deliverable` null: byte-identical to still-loading. A consultant
// watching a permanently-spinning score card could not tell in-flight from
// failed from never-attempted.
//
// These assert the DISTINGUISHABILITY, not a particular sentence: the point is
// that failure and loading stop being the same rendered state.
// ---------------------------------------------------------------------------

describe("CsfWorkspace supplementary-fetch failures (#292)", () => {
  it("says so when the score/gap refresh fails, rather than leaving the panels loading", async () => {
    fetchCatalog.mockResolvedValue(CATALOG);
    fetchInterviewQuestionnaire.mockResolvedValue(null);
    fetchLatestAssessment.mockResolvedValue(draft());
    // The refresh is what fails. Everything else succeeds, so a spinner here
    // would be indistinguishable from a slow network -- which is the defect.
    fetchScore.mockRejectedValue(new Error("boom-score"));
    fetchGapAnalysis.mockRejectedValue(new Error("boom-gap"));

    render(<CsfWorkspace serviceId="svc-1" serviceTitle="Atlas CSF" />);

    const note = await screen.findByTestId("csf-refresh-error");
    expect(note.textContent).toMatch(/score and gap/i);
    // Names what the consultant should distrust, not just that something broke.
    expect(note.textContent).toMatch(/out of date/i);
  });

  it("does not claim the deliverable is unfinalized when the check itself failed", async () => {
    // THE FALSE-NEGATIVE HALF, and the sharper one. The old comment here said
    // the card "shows 'not finalized yet'" -- a claim ABOUT THE SERVER made on
    // a request that failed. A consultant can act on it by finalizing twice.
    fetchCatalog.mockResolvedValue(CATALOG);
    fetchInterviewQuestionnaire.mockResolvedValue(null);
    fetchLatestAssessment.mockResolvedValue(draft());
    fetchScore.mockResolvedValue(SCORE);
    fetchGapAnalysis.mockResolvedValue(GAP);
    vi.mocked(csfClient.fetchLatestDeliverable).mockRejectedValue(
      new Error("boom-deliverable"),
    );

    render(<CsfWorkspace serviceId="svc-2" serviceTitle="Atlas CSF" />);

    const note = await screen.findByTestId("csf-refresh-error");
    expect(note.textContent).toMatch(
      /not a statement about whether one exists/i,
    );
  });

  it("keeps a failed interview fetch on screen through a SUCCESSFUL score refresh", async () => {
    // THE CLOBBERING HALF (#292, found by the adversarial review of d25caf7).
    // Not a race -- the ordinary path. `initialLoad` notes the interview
    // failure, then `fetchLatestAssessment` succeeds, then
    // `refreshScoreAndGap` succeeds and, with one shared slot, cleared it
    // three statements later. Every time.
    //
    // The consequence is the exact state the sentence was written to deny: 106
    // subcategories rendering no prompts, with nothing on screen to say the
    // prompts failed to load rather than not existing.
    fetchCatalog.mockResolvedValue(CATALOG);
    fetchInterviewQuestionnaire.mockRejectedValue(new Error("prompts 500"));
    fetchLatestAssessment.mockResolvedValue(draft());
    fetchScore.mockResolvedValue(SCORE);
    fetchGapAnalysis.mockResolvedValue(GAP);
    vi.mocked(csfClient.fetchLatestDeliverable).mockResolvedValue(null);

    render(<CsfWorkspace serviceId="svc-4" serviceTitle="Atlas CSF" />);

    // Wait for the workspace to settle, so this cannot pass vacuously on a
    // notice that has simply not been cleared YET. The deliverable fetch is
    // the last thing initialLoad does; the heading proves the assessment
    // arrived and the score refresh ran.
    await screen.findByText(/Atlas CSF/);
    expect(fetchScore).toHaveBeenCalled();
    expect(vi.mocked(csfClient.fetchLatestDeliverable)).toHaveBeenCalled();

    const note = await screen.findByTestId("csf-refresh-error");
    expect(note.textContent).toMatch(/which is not the same as having none/i);
  });

  it("shows BOTH failures when two different fetches fail", async () => {
    // One slot can hold one fact. Keying is what makes this assertion
    // possible at all: with a single string the second failure overwrote the
    // first and the consultant was told about whichever lost the race.
    fetchCatalog.mockResolvedValue(CATALOG);
    fetchInterviewQuestionnaire.mockRejectedValue(new Error("prompts 500"));
    fetchLatestAssessment.mockResolvedValue(draft());
    fetchScore.mockResolvedValue(SCORE);
    fetchGapAnalysis.mockResolvedValue(GAP);
    vi.mocked(csfClient.fetchLatestDeliverable).mockRejectedValue(
      new Error("deliverable 500"),
    );

    render(<CsfWorkspace serviceId="svc-5" serviceTitle="Atlas CSF" />);

    const note = await screen.findByTestId("csf-refresh-error");
    await vi.waitFor(() => {
      expect(note.textContent).toMatch(/which is not the same as having none/i);
      expect(note.textContent).toMatch(
        /not a statement about whether one exists/i,
      );
    });
  });

  it("withdraws a failure notice once THAT fetch succeeds", async () => {
    // THE OTHER HALF (#292). Three of the four workspaces never cleared at
    // all, so one transient failure pinned a permanent "may be out of date"
    // warning over figures that had since refreshed correctly -- a notice that
    // outlives its cause is furniture, and a reader learns to skip it.
    //
    // Driven through the discard path, which is a real second refresh: the
    // post-discard refetch returns the prior APPROVED version, so
    // refreshScoreAndGap runs again. The score fetch fails the first time and
    // succeeds the second.
    fetchCatalog.mockResolvedValue(CATALOG);
    fetchInterviewQuestionnaire.mockResolvedValue(null);
    const approvedPrior = {
      ...draftWithAnswers(),
      id: "assess-prior",
      status: "approved",
    } as unknown as CsfAssessment;
    fetchLatestAssessment
      .mockResolvedValueOnce(draftWithAnswers())
      .mockResolvedValue(approvedPrior);
    fetchScore
      .mockRejectedValueOnce(new Error("score 503"))
      .mockResolvedValue(SCORE);
    fetchGapAnalysis.mockResolvedValue(GAP);
    vi.mocked(csfClient.fetchLatestDeliverable).mockResolvedValue(null);
    discardAssessment.mockResolvedValue({
      ...draftWithAnswers(),
      status: "discarded",
    } as unknown as CsfAssessment);

    const { container } = render(
      <CsfWorkspace serviceId="svc-6" serviceTitle="Atlas CSF" />,
    );

    // The first refresh failed and said so.
    const note = await screen.findByTestId("csf-refresh-error");
    expect(note.textContent).toMatch(/may be out of date/i);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Discard draft" }));
    });
    const dialog = container.querySelector("dialog") as HTMLDialogElement;
    await act(async () => {
      fireEvent.click(
        within(dialog).getByRole("button", { name: "Yes, discard" }),
      );
    });

    // The second refresh succeeded, so the notice is withdrawn -- and the
    // second call is asserted, so this cannot pass on a refresh that never ran.
    expect(fetchScore).toHaveBeenCalledTimes(2);
    await vi.waitFor(() => {
      expect(screen.queryByTestId("csf-refresh-error")).toBeNull();
    });
  });

  it("stays silent when every supplementary fetch succeeds", async () => {
    // THE OTHER HALF. A notice that always renders is furniture, and a reader
    // learns to skip it -- which is worse than none, because the one time it
    // matters it looks the same.
    fetchCatalog.mockResolvedValue(CATALOG);
    fetchInterviewQuestionnaire.mockResolvedValue(null);
    fetchLatestAssessment.mockResolvedValue(draft());
    fetchScore.mockResolvedValue(SCORE);
    fetchGapAnalysis.mockResolvedValue(GAP);
    vi.mocked(csfClient.fetchLatestDeliverable).mockResolvedValue(null);

    render(<CsfWorkspace serviceId="svc-3" serviceTitle="Atlas CSF" />);

    // ASSERT WHAT MUST APPEAR BEFORE WHAT MUST NOT.
    //
    // This waited on `/Atlas CSF/` alone, which is the <h1> and renders in the
    // FIRST PAINT, before any fetch settles -- so the negative below could be
    // satisfied by a page that had not yet had the chance to render a notice.
    // `toBeNull()` on a page still fetching passes vacuously, and this is the
    // one test that would catch an always-rendering banner.
    //
    // Wait on the last fetch in the chain instead. Its sibling tests in this
    // file already do this; this one did not, which is why it was the weak one.
    await screen.findByText(/Atlas CSF/);
    await vi.waitFor(() => expect(fetchScore).toHaveBeenCalled());
    await vi.waitFor(() =>
      expect(csfClient.fetchLatestDeliverable).toHaveBeenCalled(),
    );
    expect(screen.queryByTestId("csf-refresh-error")).toBeNull();
  });
});
