import "@testing-library/jest-dom/vitest";

import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as techDebtClient from "@/lib/tech_debt/client";

import { TechDebtWorkspace } from "./TechDebtWorkspace";

/**
 * #1376: a section is a URL segment, so moving between sections remounts the
 * workspace. What an extraction left behind (the #550 lock, and an error the
 * reader has not seen) must survive that, or the sentence "Extracting stays
 * off on this page until you reload" is false the moment the reader follows
 * the copy to Review and comes back.
 */

vi.mock("@/lib/tech_debt/client", () => ({
  TechDebtProxyError: class extends Error {},
  proxyMessage: (err: unknown, fallback: string) => {
    const message = (err as { payload?: { error?: { message?: string } } })
      ?.payload?.error?.message;
    return message ?? fallback;
  },
  addCapabilityComponents: vi.fn(),
  confirmExcludedRow: vi.fn(),
  includeExcludedRow: vi.fn(),
  approveCapabilityList: vi.fn(),
  discardCapabilityList: vi.fn(),
  extractCapabilities: vi.fn(),
  // #645: the page reads the service's runs on load and polls one it
  // follows. No run, by default.
  fetchTechDebtRun: vi.fn(),
  fetchTechDebtRunSummary: vi.fn(() =>
    Promise.resolve({ running: null, latest: null, last_completed: null }),
  ),
  fetchConsolidationPlan: vi.fn(),
  fetchLatestDeliverable: vi.fn(),
  fetchLatestList: vi.fn(),
  fetchOverlapAnalysis: vi.fn(),
}));
// AI is live, so an upload extracts on its own (the path #509 gates).
vi.mock("@/lib/admin/aiStatus", () => ({
  useAiStatus: () => ({
    status: null,
    phase: "ready",
    settled: async () => ({ ready: true }),
  }),
  hasAcknowledgedOffline: () => false,
}));
vi.mock("@/lib/stages/client", () => ({
  useServiceStages: () => ({ phase: { kind: "loading" }, stages: null }),
}));
// The Dropzone stands in as a button that reports a finished upload.
vi.mock("@/components/intake/Dropzone", () => ({
  Dropzone: ({ onUploaded }: { onUploaded: (a: { id: string }) => void }) => (
    <button type="button" onClick={() => onUploaded({ id: "artifact-2" })}>
      finish upload
    </button>
  ),
}));
vi.mock("@/components/intake/RedactionDisclosure", () => ({
  RedactionDisclosure: () => null,
}));
vi.mock("./ConsolidationPlanCard", () => ({
  ConsolidationPlanCard: () => null,
}));
vi.mock("./DeliverableCard", () => ({ DeliverableCard: () => null }));
vi.mock("./DiscardDraftButton", () => ({ DiscardDraftButton: () => null }));
// Stands in for the "Extract from this" button, carrying the prop that
// disables the real one (pinned in IntakeDocumentsPanel.test.tsx).
vi.mock("./IntakeDocumentsPanel", () => ({
  IntakeDocumentsPanel: ({
    onExtract,
    extractBlocked,
  }: {
    onExtract: (artifactId: string) => void;
    extractBlocked?: boolean;
  }) => (
    <button
      type="button"
      disabled={extractBlocked === true}
      onClick={() => onExtract("artifact-1")}
    >
      extract by hand
    </button>
  ),
}));
vi.mock("./OverlapDashboard", () => ({ OverlapDashboard: () => null }));
vi.mock("./ProgressStages", () => ({ ProgressStages: () => null }));
vi.mock("./SecurityClassificationQueue", () => ({
  SecurityClassificationQueue: () => null,
}));
vi.mock("./EditableCapabilityTable", () => ({
  EditableCapabilityTable: () => null,
}));

const extractCapabilities = vi.mocked(techDebtClient.extractCapabilities);

/** What `lib/tech_debt/client.ts` throws: its class, envelope on `.payload`. */
function proxyRefusal(status: number, reason: string, message: string): Error {
  const ProxyError = techDebtClient.TechDebtProxyError as unknown as new (
    m: string,
  ) => Error;
  return Object.assign(new ProxyError(`Tech-debt proxy ${status}`), {
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
  "We couldn't confirm whether the extraction finished. It may still complete and create a draft capability list. Reload the page later and check Review before extracting again. Extracting stays off on this page until you reload.";

beforeEach(() => {
  vi.mocked(techDebtClient.fetchLatestList).mockResolvedValue(null as never);
  vi.mocked(techDebtClient.fetchLatestDeliverable).mockResolvedValue(null);
  extractCapabilities.mockReset();
});

async function extractInInputs(serviceId: string, err: Error): Promise<void> {
  extractCapabilities.mockRejectedValueOnce(err);
  render(
    <TechDebtWorkspace
      serviceId={serviceId}
      serviceTitle="TD"
      section="inputs"
    />,
  );
  const button = await screen.findByRole("button", { name: "extract by hand" });
  await act(async () => {
    fireEvent.click(button);
  });
}

describe("what an extraction left behind survives a section change (#1376)", () => {
  it("keeps the outcome-unknown lock and its band after leaving Inputs and returning", async () => {
    await extractInInputs("svc-1376-lock", OUTCOME_UNKNOWN);
    expect(await screen.findByText(COPY)).toBeInTheDocument();
    cleanup();

    render(
      <TechDebtWorkspace
        serviceId="svc-1376-lock"
        serviceTitle="TD"
        section="inputs"
      />,
    );
    expect(await screen.findByText(COPY)).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: "extract by hand" }),
    ).toBeDisabled();
    // The upload's own automatic extraction is locked too, not just the button.
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "finish upload" }));
    });
    expect(extractCapabilities).toHaveBeenCalledTimes(1);
  });

  it("shows a refusal the reader has not seen when they come back to AI draft", async () => {
    await extractInInputs("svc-1376-error", new Error("the extractor refused"));
    expect(
      await screen.findByText("the extractor refused"),
    ).toBeInTheDocument();
    cleanup();

    render(
      <TechDebtWorkspace
        serviceId="svc-1376-error"
        serviceTitle="TD"
        section="ai-draft"
      />,
    );
    expect(
      await screen.findByText("the extractor refused"),
    ).toBeInTheDocument();
  });

  it("does not carry one service's lock to another service", async () => {
    await extractInInputs("svc-1376-a", OUTCOME_UNKNOWN);
    await screen.findByText(COPY);
    cleanup();
    render(
      <TechDebtWorkspace
        serviceId="svc-1376-b"
        serviceTitle="TD"
        section="inputs"
      />,
    );
    expect(
      await screen.findByRole("button", { name: "extract by hand" }),
    ).toBeEnabled();
    expect(screen.queryByText(COPY)).toBeNull();
  });
});
