import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as ztClient from "@/lib/zt/client";
import type {
  GapAnalysis,
  ZtAssessment,
  ZtCatalog,
  ZtScoreSummary,
} from "@/lib/zt/types";

import { ZtWorkspace } from "./ZtWorkspace";

/**
 * #185 -- the score and gap fetches were COUPLED, and the typed reason was
 * DISCARDED.
 *
 * THIS FILE IS NEW. `ZtWorkspace` is the site #185 was filed against and it
 * had no component-level test of its own; the only coverage was
 * `normalizeTarget.test.ts`, which calls a pure function. A pure-function test
 * cannot see either defect here, because both live in the wiring: which
 * combinator runs the fetches, and what is done with a rejection. `CLAUDE.md`
 * is explicit that the surface a consultant reaches is where the assertion
 * belongs -- "a resolver and a pure function are not that surface".
 *
 * The CSF twin has the same tests in `csf/CsfWorkspace.test.tsx`. They are
 * duplicated rather than shared because the two workspaces are separate
 * components with separate clients and separate copy; a shared helper would
 * hide exactly the divergence the twin-sweep rule exists to catch.
 */

vi.mock("@/lib/zt/client", () => ({
  ZtProxyError: class extends Error {},
  fetchCatalog: vi.fn(),
  fetchLatestAssessment: vi.fn(),
  fetchLatestDeliverable: vi.fn(),
  fetchScore: vi.fn(),
  fetchGapAnalysis: vi.fn(),
  createAssessment: vi.fn(),
  approveAssessment: vi.fn(),
  discardAssessment: vi.fn(),
  patchAnswer: vi.fn(),
  runZtAi: vi.fn(),
  finalizeZtDeliverable: vi.fn(),
  releaseZtDeliverable: vi.fn(),
}));

// The six-stage progress strip fetches on its own; stub it to a settled state
// so the only requests in play are the workspace's own.
vi.mock("@/lib/stages/client", () => ({
  useServiceStages: () => ({ phase: "ready", stages: null }),
}));

// Children that fetch or render heavy trees. Stubbed so a failure inside one
// cannot be mistaken for the banner assertions below passing or failing.
vi.mock("./ZtScoreCard", () => ({ ZtScoreCard: () => null }));
vi.mock("./ZtGapList", () => ({ ZtGapList: () => null }));
vi.mock("./ZtRoadmapCard", () => ({ ZtRoadmapCard: () => null }));
vi.mock("./ZtQuestionnaire", () => ({ ZtQuestionnaire: () => null }));
vi.mock("./ZtDeliverableCard", () => ({ ZtDeliverableCard: () => null }));
vi.mock("./ZtRunAiAccounting", () => ({
  ZtRunAiAccounting: () => null,
  lostValueCount: () => 0,
}));
vi.mock("@/components/messages/MessageThread", () => ({
  MessageThread: () => null,
}));
vi.mock("@/components/admin/StaleDocsNudge", () => ({
  StaleDocsNudge: () => null,
}));

const fetchCatalog = vi.mocked(ztClient.fetchCatalog);
const fetchLatestAssessment = vi.mocked(ztClient.fetchLatestAssessment);
const fetchScore = vi.mocked(ztClient.fetchScore);
const fetchGapAnalysis = vi.mocked(ztClient.fetchGapAnalysis);

const CATALOG = { pillars: [], stages: [] } as unknown as ZtCatalog;
const SCORE = {} as unknown as ZtScoreSummary;
const GAP = {} as unknown as GapAnalysis;

function draft(): ZtAssessment {
  return {
    id: "zt-assess-1",
    status: "draft",
    version: 1,
    answers: [],
    client_target_stage: 3,
    documents_stale: false,
  } as unknown as ZtAssessment;
}

/**
 * A rejection shaped like the one `lib/zt/client.ts` actually throws.
 *
 * Copied off the PRODUCER, not written to suit the reader: `routes/zt.py`
 * raises an `HTTPException(422, detail={"reason": "target_stage_out_of_range",
 * "message": ...})` whose message names the framework and the offending value,
 * and `_handle_http_exception` rewraps it into the `{error: {...}}` envelope.
 * The proxy class discards that reason into its own internal label and keeps
 * the real payload alongside. A fixture carrying the sentence in `message`
 * would agree with a broken implementation by construction.
 */
function typedRefusal(status: number, reason: string, message: string): Error {
  const err = new Error("ZT proxy " + String(status)) as Error & {
    status: number;
    payload: unknown;
  };
  err.status = status;
  err.payload = {
    error: { code: status, correlation_id: "c-185", reason, message },
  };
  return err;
}

function renderWorkspace(serviceId: string): void {
  render(
    <ZtWorkspace
      serviceId={serviceId}
      framework="dod_ztra"
      serviceTitle="Atlas Zero Trust"
    />,
  );
}

describe("ZtWorkspace maturity/gap are refreshed independently (#185)", () => {
  it("keeps the maturity score when only the gap fetch fails, and blames the gap alone", async () => {
    fetchCatalog.mockResolvedValue(CATALOG);
    fetchLatestAssessment.mockResolvedValue(draft());
    vi.mocked(ztClient.fetchLatestDeliverable).mockResolvedValue(null);
    // The score SUCCEEDS. Under `Promise.all` its result was thrown away with
    // the gap's rejection, costing a panel that does not read the target at
    // all.
    fetchScore.mockResolvedValue(SCORE);
    fetchGapAnalysis.mockRejectedValue(new TypeError("fetch failed"));

    renderWorkspace("svc-185-zt-a");

    const note = await screen.findByTestId("zt-refresh-error");
    expect(note.textContent).toMatch(/gap/i);
    // THE DECOUPLING. The old single message read "Couldn't refresh the
    // maturity and gap panels", so this is the line that goes red on a revert
    // to `Promise.all`. Safe as a negative because the positive above has
    // already settled the banner.
    expect(note.textContent).not.toMatch(/maturity/i);
    // And the caught value's own text is never copy.
    expect(note.textContent).not.toContain("fetch failed");
  });

  it("puts the framework's own refusal on screen, not a fixed generic", async () => {
    fetchCatalog.mockResolvedValue(CATALOG);
    fetchLatestAssessment.mockResolvedValue(draft());
    vi.mocked(ztClient.fetchLatestDeliverable).mockResolvedValue(null);
    fetchScore.mockResolvedValue(SCORE);
    fetchGapAnalysis.mockRejectedValue(
      typedRefusal(
        422,
        "target_stage_out_of_range",
        "dod_ztra has stages 1-3; target_stage=4 is not one of them.",
      ),
    );

    renderWorkspace("svc-185-zt-b");

    const note = await screen.findByTestId("zt-refresh-error");
    // THE PRECISION #125 ADDED. The generic named neither the framework nor
    // the offending value, so a consultant could not tell what to change.
    expect(note.textContent).toContain(
      "dod_ztra has stages 1-3; target_stage=4 is not one of them.",
    );
    // Never the internal label the proxy class puts in its own `message`.
    expect(note.textContent).not.toContain("ZT proxy");
  });

  it("blames the maturity panel alone when only the score fetch fails", async () => {
    // THE OTHER DIRECTION. Without it, a fix that gave only the gap its own
    // branch would pass both tests above while the score still dragged the gap
    // down with it.
    fetchCatalog.mockResolvedValue(CATALOG);
    fetchLatestAssessment.mockResolvedValue(draft());
    vi.mocked(ztClient.fetchLatestDeliverable).mockResolvedValue(null);
    fetchScore.mockRejectedValue(new TypeError("fetch failed"));
    fetchGapAnalysis.mockResolvedValue(GAP);

    renderWorkspace("svc-185-zt-c");

    const note = await screen.findByTestId("zt-refresh-error");
    expect(note.textContent).toMatch(/maturity/i);
    expect(note.textContent).not.toMatch(/gap/i);
    expect(note.textContent).toMatch(/out of date/i);
  });

  it("says nothing when both refreshes succeed", async () => {
    // THE POSITIVE CONTROL. Without it, a banner that rendered unconditionally
    // would satisfy all three tests above.
    fetchCatalog.mockResolvedValue(CATALOG);
    fetchLatestAssessment.mockResolvedValue(draft());
    vi.mocked(ztClient.fetchLatestDeliverable).mockResolvedValue(null);
    fetchScore.mockResolvedValue(SCORE);
    fetchGapAnalysis.mockResolvedValue(GAP);

    renderWorkspace("svc-185-zt-d");

    // ASSERT WHAT MUST APPEAR BEFORE WHAT MUST NOT: `toBeNull()` on a page
    // still fetching passes vacuously.
    await screen.findByText(/Atlas Zero Trust/);
    await vi.waitFor(() => expect(fetchScore).toHaveBeenCalled());
    await vi.waitFor(() => expect(fetchGapAnalysis).toHaveBeenCalled());
    expect(screen.queryByTestId("zt-refresh-error")).toBeNull();
  });
});
