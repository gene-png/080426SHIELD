import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as attackClient from "@/lib/attack/client";
import type {
  AttackAssessment,
  AttackCatalog,
  AttackHeatmap,
} from "@/lib/attack/types";

import { AttackWorkspace } from "./AttackWorkspace";

// Deterministic + offline: the ATT&CK client lib is fully mocked and every
// child that fetches on its own is stubbed, so the only requests in play are
// the workspace's own. Each test drives the exact resolution ordering the
// reqSeq stale-fetch guard exists to defend against.
vi.mock("@/lib/attack/client", () => ({
  AttackProxyError: class extends Error {},
  fetchCatalog: vi.fn(),
  fetchHeatmap: vi.fn(),
  fetchLatestAssessment: vi.fn(),
  fetchLatestDeliverable: vi.fn(),
  createAssessment: vi.fn(),
  approveAssessment: vi.fn(),
  patchCoverage: vi.fn(),
  runAttackAi: vi.fn(),
}));

vi.mock("./AttackDeliverableCard", () => ({
  AttackDeliverableCard: () => null,
}));
vi.mock("./AttackHeatmapCard", () => ({ AttackHeatmapCard: () => null }));
vi.mock("./AttackMatrix", () => ({ AttackMatrix: () => null }));
vi.mock("./AttackTechniquePanel", () => ({ AttackTechniquePanel: () => null }));
vi.mock("@/components/messages/MessageThread", () => ({
  MessageThread: () => null,
}));
vi.mock("@/components/admin/StaleDocsNudge", () => ({
  StaleDocsNudge: () => null,
}));
vi.mock("@/components/admin/AiPreviewButton", () => ({
  AiPreviewButton: () => null,
}));

const fetchCatalog = vi.mocked(attackClient.fetchCatalog);
const fetchHeatmap = vi.mocked(attackClient.fetchHeatmap);
const fetchLatestAssessment = vi.mocked(attackClient.fetchLatestAssessment);
const createAssessment = vi.mocked(attackClient.createAssessment);

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

const CATALOG = {
  techniques: [],
  coverage_definitions: [],
} as unknown as AttackCatalog;
const HEATMAP = { by_tactic: [] } as unknown as AttackHeatmap;

function draft(): AttackAssessment {
  return {
    id: "assess-1",
    status: "draft",
    version: 1,
    coverage: [],
    documents_stale: false,
  } as unknown as AttackAssessment;
}

describe("AttackWorkspace reqSeq stale-fetch guard", () => {
  it("discards the slow mount assessment GET after a newer create", async () => {
    fetchCatalog.mockResolvedValue(CATALOG);
    // The mount's latest-assessment GET stays in flight while the user starts a
    // fresh assessment — it will resolve LAST with the pre-create null.
    const latest = deferred<AttackAssessment | null>();
    fetchLatestAssessment.mockReturnValue(latest.promise);
    createAssessment.mockResolvedValue(draft());
    fetchHeatmap.mockResolvedValue(HEATMAP);

    render(<AttackWorkspace serviceId="svc-1" serviceTitle="Atlas ATT&CK" />);

    const start = await screen.findByRole("button", {
      name: "Start assessment",
    });

    await act(async () => {
      fireEvent.click(start);
    });
    // The create settles first: the fresh draft is on screen.
    await screen.findByText("Draft v1");

    // The slow mount GET now resolves with the stale pre-create null. Without
    // the guard this setAssessment(null) would clobber the created draft.
    await act(async () => {
      latest.resolve(null);
      await latest.promise;
    });

    expect(screen.getByText("Draft v1")).toBeInTheDocument();
    expect(
      screen.queryByText("No coverage assessment yet"),
    ).not.toBeInTheDocument();
  });

  it("surfaces a failed catalog load to the error state (fail loudly)", async () => {
    fetchCatalog.mockRejectedValue(new Error("boom-catalog"));
    fetchLatestAssessment.mockResolvedValue(null);

    render(<AttackWorkspace serviceId="svc-err" serviceTitle="Atlas ATT&CK" />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("boom-catalog");
  });
});
