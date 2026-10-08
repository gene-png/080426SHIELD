import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as csfClient from "@/lib/csf/client";
import type {
  CsfAssessment,
  CsfCatalog,
  CsfScoreSummary,
  EnterpriseProfile,
  GapAnalysis,
} from "@/lib/csf/types";

import { CsfWorkspace } from "./CsfWorkspace";

/**
 * #852 on the consultant's workspace. An answer kept on ID.AM-09 (a
 * subcategory NIST CSF 2.0 does not have) is not in the questionnaire, which
 * iterates the catalog, and the API sends the approved sentence saying so.
 * Rendered as given, beside the questionnaire.
 */

vi.mock("@/lib/csf/client", () => ({
  CsfProxyError: class CsfProxyError extends Error {},
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
  fetchEnterpriseProfile: vi.fn(),
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
vi.mock("./CsfQuestionnaire", () => ({
  CsfQuestionnaire: () => <div>questionnaire</div>,
}));
vi.mock("./CsfPlaybookPanel", () => ({ CsfPlaybookPanel: () => null }));
vi.mock("@/components/messages/MessageThread", () => ({
  MessageThread: () => null,
}));
vi.mock("@/components/admin/StaleDocsNudge", () => ({
  StaleDocsNudge: () => null,
}));

const S1 =
  "1 recorded answer belongs to ID.AM-09, a subcategory NIST CSF 2.0 does not" +
  " have, so it is not scored.";

function draft(over: Partial<CsfAssessment>): CsfAssessment {
  return {
    id: "assess-852",
    service_id: "svc-852",
    status: "draft",
    version: 1,
    answers: [],
    client_target_tier: 3,
    client_profile: null,
    documents_stale: false,
    ai_source: {
      state: "none",
      sentence: "No AI suggestions were used in this assessment.",
      live_runs: 0,
      fixture_runs: 0,
    },
    ...over,
  } as unknown as CsfAssessment;
}

beforeEach(() => {
  vi.mocked(csfClient.fetchCatalog).mockResolvedValue(
    {} as unknown as CsfCatalog,
  );
  vi.mocked(csfClient.fetchInterviewQuestionnaire).mockResolvedValue(null);
  vi.mocked(csfClient.fetchLatestDeliverable).mockResolvedValue(null);
  vi.mocked(csfClient.fetchScore).mockResolvedValue(
    {} as unknown as CsfScoreSummary,
  );
  vi.mocked(csfClient.fetchGapAnalysis).mockResolvedValue(
    {} as unknown as GapAnalysis,
  );
  vi.mocked(csfClient.fetchEnterpriseProfile).mockResolvedValue({
    tiers_in_use: [],
    subcategories: [],
  } as EnterpriseProfile);
});

describe("CsfWorkspace states an answer kept on a retired subcategory (#852)", () => {
  it("renders the API's sentence beside the questionnaire", async () => {
    vi.mocked(csfClient.fetchLatestAssessment).mockResolvedValue(
      draft({ retired_answers: 1, retired_answers_note: S1 }),
    );
    render(<CsfWorkspace serviceId="svc-852" serviceTitle="Atlas CSF" />);
    expect(await screen.findByTestId("csf-retired-answers")).toHaveTextContent(
      S1,
    );
  });

  it("says nothing when nothing was kept", async () => {
    vi.mocked(csfClient.fetchLatestAssessment).mockResolvedValue(
      draft({ retired_answers: 0, retired_answers_note: null }),
    );
    render(<CsfWorkspace serviceId="svc-852" serviceTitle="Atlas CSF" />);
    expect(await screen.findByText("questionnaire")).toBeVisible();
    expect(screen.queryByTestId("csf-retired-answers")).toBeNull();
  });
});
