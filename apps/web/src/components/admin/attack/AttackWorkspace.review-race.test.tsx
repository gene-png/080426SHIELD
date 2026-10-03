import "@testing-library/jest-dom/vitest";

import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as attackClient from "@/lib/attack/client";
import type {
  AttackAssessment,
  AttackCatalog,
  AttackCoveragePatch,
  AttackCoverageRow,
  AttackHeatmap,
} from "@/lib/attack/types";

import type * as React from "react";

import { AttackWorkspace } from "./AttackWorkspace";

/**
 * #554 R3, the #808 round-3 review: a row edit made while a review POST is in
 * flight must not make the page drop the review's result. The technique panel
 * stays editable during a review, and an edit bumps the page's load counter, so
 * a counter guard on the review's result discarded a review the server had
 * recorded -- the panel kept showing reviewed rows as awaiting, and the catch
 * path said "has been refreshed" over a refresh it threw away.
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
// The matrix selects a technique; the panel edits it. Both stand-ins drive the
// workspace's own handlers.
vi.mock("./AttackMatrix", () => ({
  AttackMatrix: (props: { onSelectTechnique: (code: string) => void }) => (
    <button type="button" onClick={() => props.onSelectTechnique("T1059.001")}>
      select the other row
    </button>
  ),
}));
vi.mock("./AttackTechniquePanel", () => ({
  AttackTechniquePanel: (props: {
    coverage: AttackCoverageRow | null;
    onPatch: (patch: AttackCoveragePatch) => unknown;
  }) => (
    <>
      <span>{`notes: ${props.coverage?.notes ?? "none"}`}</span>
      <button type="button" onClick={() => void props.onPatch({ notes: "x" })}>
        edit the selected row
      </button>
    </>
  ),
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

function row(
  code: string,
  computed: "covered" | "partial",
  queued: boolean,
  notes: string | null = null,
): AttackCoverageRow {
  return {
    id: `row-${code}`,
    assessment_id: "assess-1",
    technique_code: code,
    status: "gap",
    reason_code: null,
    narrative: null,
    notes,
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
    in_review_queue: queued,
    reviewed_status: queued ? null : computed,
  };
}

function draft(
  queued: boolean,
  computed: "covered" | "partial" = "covered",
  notes: string | null = null,
) {
  return {
    id: "assess-1",
    service_id: "svc",
    status: "draft",
    version: 1,
    coverage: [
      row("T1003.001", computed, queued),
      row("T1059.001", "partial", false, notes),
    ],
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

function deferred<T>(): {
  promise: Promise<T>;
  resolve: (v: T) => void;
  reject: (e: unknown) => void;
} {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(attackClient.fetchCatalog).mockResolvedValue({
    techniques: [
      {
        id: "T1003.001",
        name: "A",
        tactics: [],
        parent_id: null,
        is_sub_technique: false,
      },
      {
        id: "T1059.001",
        name: "B",
        tactics: [],
        parent_id: null,
        is_sub_technique: false,
      },
    ],
    coverage_definitions: [],
    reason_codes: [],
  } as unknown as AttackCatalog);
  vi.mocked(attackClient.fetchHeatmap).mockResolvedValue({
    by_tactic: [],
  } as unknown as AttackHeatmap);
  vi.mocked(attackClient.fetchLatestDeliverable).mockResolvedValue(null);
  // The edit's own result: notes "x", which a snapshot read before it lacks.
  vi.mocked(attackClient.patchCoverage).mockResolvedValue(
    row("T1059.001", "partial", false, "x"),
  );
});

async function editWhileTheReviewIsInFlight(): Promise<void> {
  render(<AttackWorkspace serviceId="svc" serviceTitle="ATT&CK" />);
  const panel = await screen.findByTestId("attack-computed-review");
  fireEvent.click(
    await screen.findByRole("button", { name: "select the other row" }),
  );
  fireEvent.click(
    within(panel).getByRole("button", { name: "Mark 1 as reviewed" }),
  );
  // The review is in flight; a row edit lands and completes.
  fireEvent.click(
    screen.getByRole("button", { name: "edit the selected row" }),
  );
  await act(async () => {
    await Promise.resolve();
  });
  expect(attackClient.patchCoverage).toHaveBeenCalled();
}

function stale409(): Error {
  const ProxyError = attackClient.AttackProxyError as unknown as new (
    m: string,
  ) => Error;
  return Object.assign(new ProxyError("ATT&CK proxy 409"), {
    status: 409,
    payload: {
      error: {
        code: 409,
        reason: "computed_status_changed",
        message: "ignored by the panel",
        codes: ["T1003.001"],
      },
    },
  });
}

describe("AttackWorkspace, a row edit during a review (#554 R3)", () => {
  it("applies the review the server recorded, before the quiet re-read settles", async () => {
    // The quiet re-read is held open, so what is on screen is the REVIEW's
    // result -- a guard that dropped it would leave "1 reviewed, 1 awaiting".
    const quiet = deferred<AttackAssessment>();
    vi.mocked(attackClient.fetchLatestAssessment)
      .mockResolvedValueOnce(draft(true))
      .mockReturnValueOnce(quiet.promise);
    const review = deferred<AttackAssessment>();
    vi.mocked(attackClient.reviewComputedStatuses).mockReturnValueOnce(
      review.promise,
    );
    await editWhileTheReviewIsInFlight();
    expect(
      screen.getByText("1 reviewed, 1 awaiting review."),
    ).toBeInTheDocument();

    await act(async () => {
      review.resolve(draft(false));
    });
    expect(
      await screen.findByText("2 reviewed, 0 awaiting review."),
    ).toBeInTheDocument();
    await act(async () => {
      quiet.resolve(draft(false, "covered", "x"));
    });
  });

  it("applies the refresh it announces, before the quiet re-read settles", async () => {
    const quiet = deferred<AttackAssessment>();
    vi.mocked(attackClient.fetchLatestAssessment)
      .mockResolvedValueOnce(draft(true))
      .mockResolvedValueOnce(draft(true, "partial"))
      .mockReturnValueOnce(quiet.promise);
    const review = deferred<AttackAssessment>();
    vi.mocked(attackClient.reviewComputedStatuses).mockReturnValueOnce(
      review.promise,
    );
    await editWhileTheReviewIsInFlight();

    await act(async () => {
      review.reject(stale409());
    });
    expect(
      await screen.findByText(
        "The computed status of some techniques changed after the panel loaded (T1003.001). The panel has been refreshed; review again.",
      ),
    ).toBeInTheDocument();
    // What it says it refreshed is what it shows: the moved status, Partial.
    const panel = screen.getByTestId("attack-computed-review");
    expect(within(panel).getByText("Partial")).toBeInTheDocument();
    expect(within(panel).queryByText("Covered")).toBeNull();
    await act(async () => {
      quiet.resolve(draft(true, "partial", "x"));
    });
  });

  it("re-reads quietly when the review's snapshot predates an edit made during it", async () => {
    vi.mocked(attackClient.fetchLatestAssessment)
      .mockResolvedValueOnce(draft(true))
      .mockResolvedValueOnce(draft(false, "covered", "x"));
    const review = deferred<AttackAssessment>();
    vi.mocked(attackClient.reviewComputedStatuses).mockReturnValueOnce(
      review.promise,
    );
    await editWhileTheReviewIsInFlight();
    // The edit's own result is on screen before the older snapshot lands.
    expect(screen.getByText("notes: x")).toBeInTheDocument();
    await act(async () => {
      review.resolve(draft(false));
    });
    await waitFor(() =>
      expect(attackClient.fetchLatestAssessment).toHaveBeenCalledTimes(2),
    );
    expect(await screen.findByText("notes: x")).toBeInTheDocument();
  });

  it("re-reads quietly when the 409 re-read predates an edit made during it", async () => {
    vi.mocked(attackClient.fetchLatestAssessment)
      .mockResolvedValueOnce(draft(true))
      .mockResolvedValueOnce(draft(true, "partial"))
      .mockResolvedValueOnce(draft(true, "partial", "x"));
    const review = deferred<AttackAssessment>();
    vi.mocked(attackClient.reviewComputedStatuses).mockReturnValueOnce(
      review.promise,
    );
    await editWhileTheReviewIsInFlight();
    await act(async () => {
      review.reject(stale409());
    });
    await waitFor(() =>
      expect(attackClient.fetchLatestAssessment).toHaveBeenCalledTimes(3),
    );
    expect(await screen.findByText("notes: x")).toBeInTheDocument();
  });

  it("re-reads quietly when the edit was already in flight at the click", async () => {
    // Round 5, F1: the edit started BEFORE the review, so no edit "started
    // since" the review began; the review's snapshot (notes null) lands after
    // the edit (notes "x") and would revert it with nothing re-reading.
    vi.mocked(attackClient.fetchLatestAssessment)
      .mockResolvedValueOnce(draft(true))
      .mockResolvedValueOnce(draft(false, "covered", "x"));
    const patch = deferred<AttackCoverageRow>();
    vi.mocked(attackClient.patchCoverage).mockReturnValueOnce(patch.promise);
    const review = deferred<AttackAssessment>();
    vi.mocked(attackClient.reviewComputedStatuses).mockReturnValueOnce(
      review.promise,
    );
    render(<AttackWorkspace serviceId="svc" serviceTitle="ATT&CK" />);
    const panel = await screen.findByTestId("attack-computed-review");
    fireEvent.click(
      await screen.findByRole("button", { name: "select the other row" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "edit the selected row" }),
    );
    fireEvent.click(
      within(panel).getByRole("button", { name: "Mark 1 as reviewed" }),
    );
    await act(async () => {
      patch.resolve(row("T1059.001", "partial", false, "x"));
    });
    await act(async () => {
      review.resolve(draft(false));
    });
    await waitFor(() =>
      expect(attackClient.fetchLatestAssessment).toHaveBeenCalledTimes(2),
    );
    expect(await screen.findByText("notes: x")).toBeInTheDocument();
  });

  it("re-reads quietly when an edit in flight at the click meets a 409", async () => {
    // Round 6, F2: the 409 branch's re-read must not depend on an edit having
    // started since the click either.
    vi.mocked(attackClient.fetchLatestAssessment)
      .mockResolvedValueOnce(draft(true))
      .mockResolvedValueOnce(draft(true, "partial"))
      .mockResolvedValueOnce(draft(true, "partial", "x"));
    const patch = deferred<AttackCoverageRow>();
    vi.mocked(attackClient.patchCoverage).mockReturnValueOnce(patch.promise);
    const review = deferred<AttackAssessment>();
    vi.mocked(attackClient.reviewComputedStatuses).mockReturnValueOnce(
      review.promise,
    );
    render(<AttackWorkspace serviceId="svc" serviceTitle="ATT&CK" />);
    const panel = await screen.findByTestId("attack-computed-review");
    fireEvent.click(
      await screen.findByRole("button", { name: "select the other row" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "edit the selected row" }),
    );
    fireEvent.click(
      within(panel).getByRole("button", { name: "Mark 1 as reviewed" }),
    );
    await act(async () => {
      patch.resolve(row("T1059.001", "partial", false, "x"));
    });
    await act(async () => {
      review.reject(stale409());
    });
    await waitFor(() =>
      expect(attackClient.fetchLatestAssessment).toHaveBeenCalledTimes(3),
    );
    expect(await screen.findByText("notes: x")).toBeInTheDocument();
  });

  it("says nothing was saved-or-not when the quiet re-read after a refused review fails", async () => {
    // Round 6: after a REFUSED review nothing was saved, so the note claims no
    // save -- only that what is shown may be out of date.
    vi.mocked(attackClient.fetchLatestAssessment)
      .mockResolvedValueOnce(draft(true))
      .mockResolvedValueOnce(draft(true, "partial"))
      .mockRejectedValueOnce(new Error("down"));
    vi.mocked(attackClient.reviewComputedStatuses).mockRejectedValueOnce(
      stale409(),
    );
    render(<AttackWorkspace serviceId="svc" serviceTitle="ATT&CK" />);
    const panel = await screen.findByTestId("attack-computed-review");
    fireEvent.click(
      within(panel).getByRole("button", { name: "Mark 1 as reviewed" }),
    );
    expect(
      await screen.findByText(
        "The assessment could not be re-read, so what is shown may be out of date. Reload to see it.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Your change was saved/)).toBeNull();
  });
});
