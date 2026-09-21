import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as techDebtClient from "@/lib/tech_debt/client";
import type {
  CapabilityItem,
  CapabilityList,
  ConsolidationPlanSummary,
  OverlapAnalysis,
} from "@/lib/tech_debt/types";

import { TechDebtWorkspace } from "./TechDebtWorkspace";

// Deterministic + offline: the Tech Debt client lib is fully mocked and every
// child that fetches on its own is stubbed, so the only requests in play are
// the workspace's own -- the same construction the CSF and ATT&CK workspace
// tests use. Each test drives an exact resolution ordering.
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

vi.mock("@/lib/admin/aiStatus", () => ({
  useAiStatus: () => ({ status: null }),
  hasAcknowledgedOffline: () => true,
}));
vi.mock("@/lib/stages/client", () => ({
  useServiceStages: () => ({ phase: { kind: "loading" }, stages: null }),
}));

vi.mock("@/components/intake/Dropzone", () => ({ Dropzone: () => null }));
vi.mock("@/components/intake/RedactionDisclosure", () => ({
  RedactionDisclosure: () => null,
}));
vi.mock("./ConsolidationPlanCard", () => ({
  ConsolidationPlanCard: () => null,
}));
vi.mock("./DeliverableCard", () => ({ DeliverableCard: () => null }));
vi.mock("./DiscardDraftButton", () => ({ DiscardDraftButton: () => null }));
vi.mock("./IntakeDocumentsPanel", () => ({ IntakeDocumentsPanel: () => null }));
vi.mock("./OverlapDashboard", () => ({ OverlapDashboard: () => null }));
vi.mock("./ProgressStages", () => ({ ProgressStages: () => null }));
vi.mock("./SecurityClassificationQueue", () => ({
  SecurityClassificationQueue: () => null,
}));

// The one child that is NOT inert: it owns the inline edit, and the inline
// edit is what fires a SECOND overlapping refreshOverlap. A button standing in
// for the row editor is what lets the test drive two edits in a controlled
// order -- the real table's own behaviour is covered elsewhere.
vi.mock("./EditableCapabilityTable", () => ({
  EditableCapabilityTable: ({
    onItemUpdate,
  }: {
    onItemUpdate: (next: CapabilityItem) => void;
  }) => (
    <button
      type="button"
      onClick={() =>
        onItemUpdate({
          id: "item-1",
          name: "edited",
        } as unknown as CapabilityItem)
      }
    >
      edit a row
    </button>
  ),
}));

const fetchLatestList = vi.mocked(techDebtClient.fetchLatestList);
const fetchOverlapAnalysis = vi.mocked(techDebtClient.fetchOverlapAnalysis);
const fetchConsolidationPlan = vi.mocked(techDebtClient.fetchConsolidationPlan);
const fetchLatestDeliverable = vi.mocked(techDebtClient.fetchLatestDeliverable);

interface Deferred<T> {
  promise: Promise<T>;
  reject: (err: unknown) => void;
}

function deferred<T>(): Deferred<T> {
  let reject!: (err: unknown) => void;
  const promise = new Promise<T>((_res, rej) => {
    reject = rej;
  });
  // Nothing awaits this until the test rejects it; an unhandled rejection
  // warning would otherwise fire before the workspace attaches its catch.
  promise.catch(() => undefined);
  return { promise, reject };
}

const OVERLAP = { groups: [] } as unknown as OverlapAnalysis;
const PLAN = { items: [] } as unknown as ConsolidationPlanSummary;

function draftList(): CapabilityList {
  return {
    id: "list-1",
    status: "draft",
    version: 1,
    items: [{ id: "item-1", name: "original" }],
    excluded_rows: [],
  } as unknown as CapabilityList;
}

describe("TechDebtWorkspace supplementary-fetch failures (#292)", () => {
  it("ignores a SUPERSEDED plan refresh that fails after a newer one succeeded", async () => {
    // `refreshOverlap` sequence-guards setOverlap, setOverlapError, setPlan
    // and setOverlapLoading -- the file's own comment names the T8 stale-fetch
    // race. The first version of the #292 fix added the ONE write that was not
    // guarded, which is the shape this test pins.
    //
    // Two inline edits ~200ms apart: #2 completes and `plan` is current and
    // correct; #1's plan fetch then rejects. An unguarded write puts a
    // permanent "the overlap figures may be out of date" warning above figures
    // that ARE up to date -- a superseded request describing a newer one.
    fetchLatestList.mockResolvedValue(draftList());
    fetchOverlapAnalysis.mockResolvedValue(OVERLAP);
    fetchLatestDeliverable.mockResolvedValue(null);

    const stale = deferred<ConsolidationPlanSummary>();
    fetchConsolidationPlan
      .mockResolvedValueOnce(PLAN) // mount
      .mockReturnValueOnce(stale.promise) // edit #1 -- still in flight
      .mockResolvedValue(PLAN); // edit #2 -- resolves first

    render(<TechDebtWorkspace serviceId="svc-1" serviceTitle="Atlas TD" />);

    const edit = await screen.findByRole("button", { name: "edit a row" });

    await act(async () => {
      fireEvent.click(edit); // edit #1: seq 2, plan fetch pending
    });
    await act(async () => {
      fireEvent.click(edit); // edit #2: seq 3, plan fetch resolves
    });

    // Not vacuous: the newest refresh really did run and really did settle.
    expect(fetchConsolidationPlan).toHaveBeenCalledTimes(3);
    expect(screen.queryByTestId("techdebt-refresh-error")).toBeNull();

    // Now the superseded request fails. It describes a state two edits old.
    await act(async () => {
      stale.reject(new Error("plan 503"));
      await Promise.resolve();
    });

    expect(screen.queryByTestId("techdebt-refresh-error")).toBeNull();
  });

  it("does say so when the NEWEST plan refresh is the one that fails", async () => {
    // THE OTHER HALF. A guard that suppresses the stale write must not also
    // suppress the live one -- that would trade a false warning for a silent
    // failure, which is the defect #292 is about.
    fetchLatestList.mockResolvedValue(draftList());
    fetchOverlapAnalysis.mockResolvedValue(OVERLAP);
    fetchLatestDeliverable.mockResolvedValue(null);
    fetchConsolidationPlan
      .mockResolvedValueOnce(PLAN) // mount
      .mockRejectedValue(new Error("plan 503")); // the edit's own refresh

    render(<TechDebtWorkspace serviceId="svc-2" serviceTitle="Atlas TD" />);

    const edit = await screen.findByRole("button", { name: "edit a row" });
    await act(async () => {
      fireEvent.click(edit);
    });

    const note = await screen.findByTestId("techdebt-refresh-error");
    expect(note.textContent).toMatch(/overlap figures/i);
  });
});
