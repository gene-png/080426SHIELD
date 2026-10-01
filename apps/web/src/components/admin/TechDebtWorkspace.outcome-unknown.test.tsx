import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as techDebtClient from "@/lib/tech_debt/client";

import { TechDebtWorkspace } from "./TechDebtWorkspace";

/**
 * #550: an extraction whose answer the proxy never saw is not a failed one.
 * Measured on #550: the api ran on after the caller gave up, wrote its
 * `llm_calls` row and created the draft list, while the page said "failed".
 * The page now says the outcome is unknown, names where the draft would
 * appear, and extracts nothing more for the rest of its life -- by button or
 * by the upload's automatic extraction.
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
  "We couldn't confirm whether the extraction finished. It may still complete and create a draft capability list. Reload the page later and check step 2, Review and correct the extracted list, before extracting again. Extracting stays off on this page until you reload.";

beforeEach(() => {
  vi.mocked(techDebtClient.fetchLatestList).mockResolvedValue(null as never);
  vi.mocked(techDebtClient.fetchLatestDeliverable).mockResolvedValue(null);
  extractCapabilities.mockReset();
  // A second extraction, if one were started, would succeed: so a revert of
  // the lock fails on the call count below, not on an unmocked call.
  extractCapabilities.mockResolvedValue({
    id: "list-2",
    status: "draft",
    version: 1,
    items: [],
    excluded_rows: [],
  } as never);
});

async function extractByHandRejectingWith(err: Error): Promise<void> {
  extractCapabilities.mockRejectedValueOnce(err);
  render(<TechDebtWorkspace serviceId="svc-550" serviceTitle="Atlas TD" />);
  const button = await screen.findByRole("button", { name: "extract by hand" });
  expect(button).toBeEnabled();
  await act(async () => {
    fireEvent.click(button);
  });
}

describe("TechDebtWorkspace, an extraction whose outcome is unknown (#550)", () => {
  it("says where the draft would appear rather than that extraction failed", async () => {
    await extractByHandRejectingWith(OUTCOME_UNKNOWN);

    expect(await screen.findByText(COPY)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "extract by hand" }),
    ).toBeDisabled();
    expect(screen.queryByText(/failed/i)).not.toBeInTheDocument();
  });

  it("does not extract again when another upload finishes", async () => {
    await extractByHandRejectingWith(OUTCOME_UNKNOWN);
    await screen.findByText(COPY);
    expect(extractCapabilities).toHaveBeenCalledTimes(1);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "finish upload" }));
    });
    await act(async () => {
      await Promise.resolve();
    });

    expect(extractCapabilities).toHaveBeenCalledTimes(1);
  });

  it("keeps extraction on after a refusal the api DID send", async () => {
    await extractByHandRejectingWith(
      proxyRefusal(409, "capability_list_draft_open", "A draft is open."),
    );

    expect(await screen.findByText("A draft is open.")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "extract by hand" }),
    ).toBeEnabled();
    expect(screen.queryByText(COPY)).not.toBeInTheDocument();
  });
});
