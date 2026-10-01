import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

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
 * #550: a ZT Run AI whose answer the proxy never saw is not a failed run, and
 * not a workspace that "couldn't load". The page says the outcome is unknown,
 * names where to check, and keeps Run AI off for the rest of its life.
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
vi.mock("@/lib/stages/client", () => ({
  useServiceStages: () => ({ phase: "ready", stages: null }),
}));
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
vi.mock("@/components/admin/RunAiGuard", () => ({
  RunAiGuard: (props: {
    onProceed: () => void;
    children: (p: { onClick: () => void }) => React.ReactNode;
  }) => props.children({ onClick: props.onProceed }),
}));
vi.mock("@/components/admin/AiPreviewButton", () => ({
  AiPreviewButton: () => null,
}));

/** What `lib/zt/client.ts` throws: its error class, envelope on `.payload`. */
function proxyRefusal(status: number, reason: string, message: string): Error {
  const ProxyError = ztClient.ZtProxyError as unknown as new (
    m: string,
  ) => Error;
  return Object.assign(new ProxyError(`ZT proxy ${status}`), {
    status,
    payload: { error: { code: status, reason, message } },
  });
}

const OUTCOME_UNKNOWN = proxyRefusal(
  504,
  "upstream_outcome_unknown",
  "We couldn't confirm whether this finished. It may still complete; check before trying again.",
);

const COPY =
  "We couldn't confirm whether the AI run finished. It may still complete and fill in capability rows. Reload the page later and check step 2, Review every capability and adjust, before running it again. Run AI stays off on this page until you reload.";

beforeEach(() => {
  vi.mocked(ztClient.fetchCatalog).mockResolvedValue({
    pillars: [],
    stages: [],
  } as unknown as ZtCatalog);
  vi.mocked(ztClient.fetchLatestAssessment).mockResolvedValue({
    id: "zt-assess-1",
    status: "draft",
    version: 1,
    answers: [],
    client_target_stage: 3,
    documents_stale: false,
  } as unknown as ZtAssessment);
  vi.mocked(ztClient.fetchLatestDeliverable).mockResolvedValue(null);
  vi.mocked(ztClient.fetchScore).mockResolvedValue(
    {} as unknown as ZtScoreSummary,
  );
  vi.mocked(ztClient.fetchGapAnalysis).mockResolvedValue(
    {} as unknown as GapAnalysis,
  );
  vi.mocked(ztClient.runZtAi).mockReset();
});

async function runAiRejectingWith(err: Error): Promise<void> {
  vi.mocked(ztClient.runZtAi).mockRejectedValueOnce(err);
  render(
    <ZtWorkspace
      serviceId="svc-550-zt"
      framework="dod_ztra"
      serviceTitle="Atlas Zero Trust"
    />,
  );
  const button = await screen.findByRole("button", { name: "Run AI" });
  expect(button).toBeEnabled();
  fireEvent.click(button);
}

describe("ZtWorkspace, a Run AI whose outcome is unknown (#550)", () => {
  it("says where to check rather than that the run failed, and keeps Run AI off", async () => {
    await runAiRejectingWith(OUTCOME_UNKNOWN);

    expect(await screen.findByText(COPY)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run AI" })).toBeDisabled();
    expect(
      screen.queryByText("Couldn't load the assessment"),
    ).not.toBeInTheDocument();
  });

  it("names a step the page renders, by its number and its title", async () => {
    // The copy sends the reader to a step. Read the number and title out of
    // the alert the page rendered, and require the page to render that step's
    // heading, so renaming or renumbering the step turns this red.
    await runAiRejectingWith(OUTCOME_UNKNOWN);
    const alert = await screen.findByText(COPY);
    const named = /check step (\d+), ([^,]+), before/.exec(
      alert.textContent ?? "",
    );
    expect(named, "the copy names no step").not.toBeNull();
    const [, number, title] = named as RegExpExecArray;
    expect(
      screen.getByRole("heading", { name: `Step ${number}: ${title}` }),
    ).toBeInTheDocument();
  });

  it("leaves Run AI on after a refusal the api DID send", async () => {
    await runAiRejectingWith(
      proxyRefusal(409, "assessment_not_draft", "Not a draft."),
    );

    expect(await screen.findByText("Not a draft.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run AI" })).toBeEnabled();
    expect(screen.queryByText(COPY)).not.toBeInTheDocument();
  });
});
