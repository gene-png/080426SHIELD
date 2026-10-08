import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as attackClient from "@/lib/attack/client";
import type {
  AttackAssessment,
  AttackCatalog,
  AttackCoveragePatch,
  AttackCoverageRow,
  AttackHeatmap,
  AttackOutsideCitation,
} from "@/lib/attack/types";

import type * as React from "react";

import { AttackWorkspace } from "./AttackWorkspace";

/**
 * #851, review finding F2: `citations_outside_subset` is ASSESSMENT-level state
 * the server derives from every row's tools, and the coverage PATCH returns
 * only the row. So after a Remove -- or any write to a tool list -- the alert
 * kept naming a tool that was gone until a full page reload, and the S3b
 * remedy it prints ("Remove the tool in the technique's panel") looked as if
 * it had not worked. The workspace re-reads the assessment instead of
 * re-deriving the list in the browser (the rule lives in
 * `app/attack/subset_drift.py`, once).
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
// The matrix selects the standalone row; the panel stand-in drives the
// workspace's own `onPatch` with each kind of write.
vi.mock("./AttackMatrix", () => ({
  AttackMatrix: (props: { onSelectTechnique: (code: string) => void }) => (
    <button type="button" onClick={() => props.onSelectTechnique("T1003")}>
      select the row
    </button>
  ),
}));
vi.mock("./AttackTechniquePanel", () => ({
  AttackTechniquePanel: (props: {
    onPatch: (patch: AttackCoveragePatch) => unknown;
  }) => (
    <>
      <button
        type="button"
        onClick={() =>
          void props.onPatch({
            remove_tool: { field: "detection_tools", name: "Legacy AV" },
          })
        }
      >
        remove the tool
      </button>
      <button
        type="button"
        onClick={() => void props.onPatch({ detection_tools: [] })}
      >
        replace the detection list
      </button>
      <button
        type="button"
        onClick={() => void props.onPatch({ locked: false })}
      >
        unlock the row
      </button>
      <button type="button" onClick={() => void props.onPatch({ notes: "x" })}>
        edit the notes
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

const LEGACY: AttackOutsideCitation = {
  technique_code: "T1003",
  field: "detection_tools",
  tool: "Legacy AV",
  locked: false,
};

function row(tools: string[]): AttackCoverageRow {
  return {
    id: "row-T1003",
    assessment_id: "assess-1",
    technique_code: "T1003",
    status: "covered",
    reason_code: null,
    narrative: null,
    notes: null,
    evidence_artifact_id: null,
    answered_by: null,
    answered_at: null,
    detection_tools: tools,
    prevention_tools: [],
    response_tools: [],
  } as unknown as AttackCoverageRow;
}

function draft(outside: AttackOutsideCitation[]): AttackAssessment {
  return {
    id: "assess-1",
    service_id: "svc",
    status: "draft",
    version: 1,
    coverage: [row(outside.length > 0 ? ["Legacy AV"] : [])],
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
    citations_outside_subset: outside,
    subset_checked: true,
  } as unknown as AttackAssessment;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(attackClient.fetchCatalog).mockResolvedValue({
    techniques: [
      // STANDALONE: no parent, so the #620 parent re-read cannot be what
      // refreshes the alert.
      {
        id: "T1003",
        name: "OS Credential Dumping",
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
  vi.mocked(attackClient.patchCoverage).mockResolvedValue(row([]));
});

async function openWithTheAlert(): Promise<void> {
  vi.mocked(attackClient.fetchLatestAssessment)
    .mockResolvedValueOnce(draft([LEGACY]))
    // What the server says once the write has landed.
    .mockResolvedValue(draft([]));
  render(<AttackWorkspace serviceId="svc" serviceTitle="ATT&CK" />);
  expect(await screen.findByTestId("attack-outside-subset")).toHaveTextContent(
    "T1003, Detection: Legacy AV",
  );
  fireEvent.click(screen.getByRole("button", { name: "select the row" }));
}

describe("AttackWorkspace, the outside-subset alert after a write (#851 F2)", () => {
  it.each([
    ["remove the tool", "remove_tool"],
    ["replace the detection list", "detection_tools"],
  ])(
    "re-reads the assessment after %s, so the alert matches the server",
    async (button, key) => {
      await openWithTheAlert();
      fireEvent.click(screen.getByRole("button", { name: button }));
      await act(async () => {
        await Promise.resolve();
      });
      expect(
        vi.mocked(attackClient.patchCoverage).mock.calls[0][1],
      ).toHaveProperty(key);
      // The positive state first: the re-read happened...
      await vi.waitFor(() =>
        expect(attackClient.fetchLatestAssessment).toHaveBeenCalledTimes(2),
      );
      // ...then the alert it carried is gone.
      expect(screen.queryByTestId("attack-outside-subset")).toBeNull();
    },
  );

  it("re-reads after the lock changes, so the alert stops calling the row locked", async () => {
    // Review N1 (round 2): the alert's "(locked, ...)" marker is read from the
    // same assessment-level list, and S3b's own remedy is "unlock the row".
    const LOCKED = { ...LEGACY, locked: true };
    vi.mocked(attackClient.fetchLatestAssessment)
      .mockResolvedValueOnce(draft([LOCKED]))
      // The server after the unlock: still outside, no longer locked.
      .mockResolvedValue(draft([LEGACY]));
    render(<AttackWorkspace serviceId="svc" serviceTitle="ATT&CK" />);
    expect(
      await screen.findByTestId("attack-outside-subset"),
    ).toHaveTextContent(
      "T1003, Detection: Legacy AV (locked, so Run AI will not change it)",
    );
    fireEvent.click(screen.getByRole("button", { name: "select the row" }));
    fireEvent.click(screen.getByRole("button", { name: "unlock the row" }));
    await vi.waitFor(() =>
      expect(attackClient.fetchLatestAssessment).toHaveBeenCalledTimes(2),
    );
    await vi.waitFor(() =>
      expect(
        screen.getByTestId("attack-outside-subset").querySelector("li")
          ?.textContent,
      ).toBe("T1003, Detection: Legacy AV"),
    );
  });

  it("does not re-read for a write that cannot move the alert", async () => {
    await openWithTheAlert();
    vi.mocked(attackClient.patchCoverage).mockResolvedValue({
      ...row(["Legacy AV"]),
      notes: "x",
    } as AttackCoverageRow);
    fireEvent.click(screen.getByRole("button", { name: "edit the notes" }));
    await vi.waitFor(() =>
      expect(attackClient.patchCoverage).toHaveBeenCalledTimes(1),
    );
    await act(async () => {
      await Promise.resolve();
    });
    expect(attackClient.fetchLatestAssessment).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("attack-outside-subset")).toBeInTheDocument();
  });
});
