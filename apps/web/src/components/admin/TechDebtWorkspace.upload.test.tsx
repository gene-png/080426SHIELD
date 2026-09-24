import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as techDebtClient from "@/lib/tech_debt/client";

import type { AiStatus } from "@/lib/admin/client";

import { TechDebtWorkspace } from "./TechDebtWorkspace";

/**
 * #509, made reachable by #472: an upload auto-starts an AI extraction, and
 * the gate that stops it when AI is offline read `status`, which is null while
 * the status request is still in flight. A null status ran the extraction with
 * no warning -- the conflation `lib/admin/aiStatus.ts` tells callers not to
 * make. Since #472 the first status read can take seconds (the ADC probe), so
 * an upload finishing inside that window was a real path. The gate now waits
 * for a SETTLED status, as the Run-AI guard does.
 */

vi.mock("@/lib/tech_debt/client", () => ({
  TechDebtProxyError: class extends Error {},
  proxyMessage: (err: unknown, fallback: string) =>
    err instanceof Error ? err.message : fallback,
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

/** What the status request will settle to, controlled per test. */
let settle!: (s: AiStatus | null) => void;
let settledStatus: Promise<AiStatus | null>;

vi.mock("@/lib/admin/aiStatus", () => ({
  // Still loading: `status` is null until the request settles.
  useAiStatus: () => ({
    status: null,
    phase: "loading",
    settled: () => settledStatus,
  }),
  hasAcknowledgedOffline: () => false,
}));
vi.mock("@/lib/stages/client", () => ({
  useServiceStages: () => ({ phase: { kind: "loading" }, stages: null }),
}));
// The Dropzone stands in as a button that reports a finished upload.
vi.mock("@/components/intake/Dropzone", () => ({
  Dropzone: ({ onUploaded }: { onUploaded: (a: { id: string }) => void }) => (
    <button type="button" onClick={() => onUploaded({ id: "artifact-1" })}>
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
// Stands in for the guarded "Extract from this" button: a manual extraction.
vi.mock("./IntakeDocumentsPanel", () => ({
  IntakeDocumentsPanel: ({
    onExtract,
  }: {
    onExtract: (artifactId: string) => void;
  }) => (
    <button type="button" onClick={() => onExtract("artifact-1")}>
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

function status(over: Partial<AiStatus>): AiStatus {
  return {
    mode: "fixture",
    provider: "anthropic",
    model: "claude-opus-5",
    ready: false,
    detail: "No API key is loaded",
    can_configure: true,
    key_source: "none",
    serves: "offline",
    ...over,
  };
}

beforeEach(() => {
  settledStatus = new Promise((resolve) => {
    settle = resolve;
  });
  vi.mocked(techDebtClient.fetchLatestList).mockResolvedValue(null as never);
  vi.mocked(techDebtClient.fetchLatestDeliverable).mockResolvedValue(null);
  extractCapabilities.mockReset();
  extractCapabilities.mockResolvedValue({
    id: "list-1",
    status: "draft",
    version: 1,
    items: [],
    excluded_rows: [],
  } as never);
});

async function uploadWhileStatusLoads() {
  render(<TechDebtWorkspace serviceId="svc-1" serviceTitle="Atlas TD" />);
  const finish = await screen.findByRole("button", { name: "finish upload" });
  await act(async () => {
    fireEvent.click(finish);
  });
}

describe("auto-extraction on upload waits for a settled AI status (#509)", () => {
  it("does not run while the status is still loading", async () => {
    await uploadWhileStatusLoads();
    expect(extractCapabilities).not.toHaveBeenCalled();
  });

  it("does not run once the status settles as offline and unacknowledged", async () => {
    await uploadWhileStatusLoads();
    await act(async () => {
      settle(status({}));
    });
    expect(extractCapabilities).not.toHaveBeenCalled();
  });

  it("runs once the status settles as live", async () => {
    await uploadWhileStatusLoads();
    await act(async () => {
      settle(status({ ready: true, serves: "live", key_source: "database" }));
    });
    expect(extractCapabilities).toHaveBeenCalledWith("svc-1", "artifact-1");
  });

  it("does not run when the status cannot be read -- the guarded button is the way in", async () => {
    // And SAYS so, rather than crashing on `null.ready`: a TypeError inside the
    // promise also stops the extraction, so "not called" alone could not tell
    // the handled case from an unhandled rejection.
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    await uploadWhileStatusLoads();
    await act(async () => {
      settle(null);
    });
    expect(extractCapabilities).not.toHaveBeenCalled();
    expect(warn).toHaveBeenCalledWith(
      "[tech-debt] AI status unreadable; not auto-extracting",
    );
    warn.mockRestore();
  });
});

// The deferred decision must not repeat an extraction the user already ran.
// Found by the e2e suite: a user who clicks "Extract from this" while the
// status is still settling got a SECOND extraction when it settled, because by
// then the acknowledgement they had just given made the auto path eligible.
describe("the deferred auto-extraction and a manual one", () => {
  it("does not extract again when the user already extracted by hand", async () => {
    await uploadWhileStatusLoads();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "extract by hand" }));
    });
    expect(extractCapabilities).toHaveBeenCalledTimes(1);
    await act(async () => {
      settle(status({ ready: true, serves: "live", key_source: "database" }));
    });
    expect(extractCapabilities).toHaveBeenCalledTimes(1);
  });

  it("still lets the user extract the same file again by hand", async () => {
    // The guard is for the DEFERRED auto path only. Discard a draft, then
    // "Extract from this" on the same file, must still extract; a check moved
    // into runExtraction would silently break that.
    await uploadWhileStatusLoads();
    for (let i = 0; i < 2; i++) {
      await act(async () => {
        fireEvent.click(
          screen.getByRole("button", { name: "extract by hand" }),
        );
      });
    }
    expect(extractCapabilities).toHaveBeenCalledTimes(2);
  });
});
