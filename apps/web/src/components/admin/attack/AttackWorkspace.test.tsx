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
// A marker rather than null, so a test can tell whether step 2 drew it (#556).
vi.mock("./AttackMatrix", () => ({
  // A button that selects a technique, so a test can drive the panel's onPatch
  // through the workspace without rendering the real matrix.
  AttackMatrix: (props: { onSelectTechnique: (code: string) => void }) => (
    <div data-testid="attack-matrix">
      <button
        type="button"
        onClick={() => props.onSelectTechnique("T1001.001")}
      >
        select sub-technique
      </button>
    </div>
  ),
}));
vi.mock("./AttackTechniquePanel", () => ({
  AttackTechniquePanel: (props: {
    onPatch: (patch: { status: string }) => void;
  }) => (
    <button type="button" onClick={() => void props.onPatch({ status: "gap" })}>
      set gap
    </button>
  ),
}));
vi.mock("@/components/messages/MessageThread", () => ({
  MessageThread: () => null,
}));
vi.mock("@/components/admin/StaleDocsNudge", () => ({
  StaleDocsNudge: () => null,
}));
vi.mock("@/components/admin/AiPreviewButton", () => ({
  AiPreviewButton: () => null,
}));
// Fetches on mount on its own; stubbed for the same reason as every other
// self-fetching child above, so the only requests in play stay the
// workspace's own. Its behaviour is covered in AttackAiInputsPanel.test.tsx.
vi.mock("./AttackAiInputsPanel", () => ({
  AttackAiInputsPanel: () => null,
}));

const fetchCatalog = vi.mocked(attackClient.fetchCatalog);
const fetchHeatmap = vi.mocked(attackClient.fetchHeatmap);
const fetchLatestAssessment = vi.mocked(attackClient.fetchLatestAssessment);
const createAssessment = vi.mocked(attackClient.createAssessment);
const patchCoverage = vi.mocked(attackClient.patchCoverage);

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
    catalog_version: "19.2",
    catalog_current: true,
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

  it("shows the API's own refusal when the assessment is on another ATT&CK catalog (#556)", async () => {
    fetchCatalog.mockResolvedValue(CATALOG);
    fetchLatestAssessment.mockResolvedValue(draft());
    const payload = {
      error: {
        reason: "attack_catalog_mismatch",
        message:
          "This assessment was scored against an ATT&CK catalog that was never recorded.",
      },
    };
    // The mocked class stores nothing, so status and payload are set explicitly.
    const refusal = Object.assign(
      new attackClient.AttackProxyError(409, payload),
      {
        status: 409,
        payload,
      },
    );
    fetchHeatmap.mockRejectedValue(refusal);

    render(
      <AttackWorkspace serviceId="svc-stale" serviceTitle="Atlas ATT&CK" />,
    );

    expect(
      await screen.findByText(
        /scored against an ATT&CK catalog that was never recorded/,
      ),
    ).toBeInTheDocument();
    // "reload to try again" is false advice for a stale assessment.
    expect(screen.queryByText(/reload to try again/)).not.toBeInTheDocument();
  });

  it("does not offer Approve on an assessment scored against another catalog (#556)", async () => {
    fetchCatalog.mockResolvedValue(CATALOG);
    fetchLatestAssessment.mockResolvedValue({
      ...draft(),
      catalog_version: null,
      catalog_current: false,
    });
    fetchHeatmap.mockResolvedValue(HEATMAP);

    render(
      <AttackWorkspace
        serviceId="svc-stale-approve"
        serviceTitle="Atlas ATT&CK"
      />,
    );

    // Steps 1, 3 and 4 each say why they are blocked.
    expect(
      await screen.findAllByText(
        /scored against a different ATT&CK catalog than the current one/,
      ),
    ).toHaveLength(3);
    expect(screen.getByRole("button", { name: /approve/i })).toBeDisabled();
    // Run AI's only outcome would be the API's 409, so it is not offered.
    expect(screen.getByRole("button", { name: "Run AI" })).toBeDisabled();
  });

  it("reads an ABSENT catalog_current as not current (#556, fail closed)", async () => {
    // Missing data defaults to unconfirmed: a response without the field must
    // not be offered Run AI, whose only outcome for a stale assessment is 409.
    const { catalog_current: _omit, ...withoutField } = draft();
    fetchCatalog.mockResolvedValue(CATALOG);
    fetchLatestAssessment.mockResolvedValue(
      withoutField as unknown as AttackAssessment,
    );
    fetchHeatmap.mockResolvedValue(HEATMAP);

    render(
      <AttackWorkspace serviceId="svc-absent" serviceTitle="Atlas ATT&CK" />,
    );

    expect(
      await screen.findByRole("button", { name: "Run AI" }),
    ).toBeDisabled();
  });

  it("offers Run AI on a current draft", async () => {
    fetchCatalog.mockResolvedValue(CATALOG);
    fetchLatestAssessment.mockResolvedValue({
      ...draft(),
      catalog_version: "19.2",
      catalog_current: true,
    });
    fetchHeatmap.mockResolvedValue(HEATMAP);

    render(
      <AttackWorkspace
        serviceId="svc-current-run"
        serviceTitle="Atlas ATT&CK"
      />,
    );

    expect(
      await screen.findByRole("button", { name: "Run AI" }),
    ).not.toBeDisabled();
  });

  it("does not draw a stale assessment's rows into the current matrix (#556)", async () => {
    fetchCatalog.mockResolvedValue(CATALOG);
    fetchLatestAssessment.mockResolvedValue({
      ...draft(),
      catalog_version: "15.1",
      catalog_current: false,
    });
    fetchHeatmap.mockResolvedValue(HEATMAP);

    render(
      <AttackWorkspace
        serviceId="svc-stale-matrix"
        serviceTitle="Atlas ATT&CK"
      />,
    );

    expect(await screen.findByTestId("attack-stale-catalog")).toHaveTextContent(
      "This assessment was scored against ATT&CK v15.1, not the current one.",
    );
    expect(screen.queryByTestId("attack-matrix")).not.toBeInTheDocument();
  });

  it("draws the matrix for a current assessment", async () => {
    fetchCatalog.mockResolvedValue(CATALOG);
    fetchLatestAssessment.mockResolvedValue({
      ...draft(),
      catalog_version: "19.2",
      catalog_current: true,
    });
    fetchHeatmap.mockResolvedValue(HEATMAP);

    render(
      <AttackWorkspace
        serviceId="svc-current-matrix"
        serviceTitle="Atlas ATT&CK"
      />,
    );

    expect(await screen.findByTestId("attack-matrix")).toBeInTheDocument();
    expect(
      screen.queryByTestId("attack-stale-catalog"),
    ).not.toBeInTheDocument();
  });

  it("keeps the generic sentence for any OTHER heatmap failure", async () => {
    fetchCatalog.mockResolvedValue(CATALOG);
    fetchLatestAssessment.mockResolvedValue(draft());
    fetchHeatmap.mockRejectedValue(
      Object.assign(
        new attackClient.AttackProxyError(500, {
          error: { reason: "something_else", message: "not shown" },
        }),
        {
          status: 500,
          payload: {
            error: { reason: "something_else", message: "not shown" },
          },
        },
      ),
    );

    render(<AttackWorkspace serviceId="svc-500" serviceTitle="Atlas ATT&CK" />);

    expect(await screen.findByText(/reload to try again/)).toBeInTheDocument();
    expect(screen.queryByText("not shown")).not.toBeInTheDocument();
  });

  it("surfaces a failed catalog load to the error state (fail loudly)", async () => {
    fetchCatalog.mockRejectedValue(new Error("boom-catalog"));
    fetchLatestAssessment.mockResolvedValue(null);

    render(<AttackWorkspace serviceId="svc-err" serviceTitle="Atlas ATT&CK" />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("boom-catalog");
  });
});

describe("AttackWorkspace, a computed parent after a child's edit (#554, D-094)", () => {
  it("refetches the assessment, so the parent's recomputed status shows", async () => {
    const child = {
      id: "c-child",
      technique_code: "T1001.001",
      status: "covered",
      pending_review: false,
    };
    const parentOld = {
      id: "c-parent",
      technique_code: "T1001",
      status: "covered",
      pending_review: false,
    };
    const before = { ...draft(), coverage: [parentOld, child] };
    const after = {
      ...draft(),
      coverage: [
        { ...parentOld, status: "gap" },
        { ...child, status: "gap" },
      ],
    };
    fetchCatalog.mockResolvedValue(CATALOG);
    fetchHeatmap.mockResolvedValue(HEATMAP);
    fetchLatestAssessment
      .mockResolvedValueOnce(before as unknown as AttackAssessment)
      .mockResolvedValueOnce(after as unknown as AttackAssessment);
    patchCoverage.mockResolvedValue({
      ...child,
      status: "gap",
    } as unknown as Awaited<ReturnType<typeof attackClient.patchCoverage>>);

    render(
      <AttackWorkspace serviceId="svc-parent" serviceTitle="Atlas ATT&CK" />,
    );
    fireEvent.click(await screen.findByText("select sub-technique"));
    fireEvent.click(await screen.findByText("set gap"));

    // The second load is the refetch; without it the parent keeps "covered".
    await vi.waitFor(() =>
      expect(fetchLatestAssessment).toHaveBeenCalledTimes(2),
    );
  });
});
