import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as ztClient from "@/lib/zt/client";
import type { ZtAssessment, ZtCatalog } from "@/lib/zt/types";

import { ZtSelfAssessment } from "./ZtSelfAssessment";

/**
 * A failed save must REVERT the optimistic write and SAY SO (#283).
 *
 * The component wrote the client's change into local state before the request,
 * then swallowed any rejection in a bare `catch {}` under the comment
 * "Best-effort optimistic save; a reload reconciles if it failed." The client
 * was never told a reload was needed, so the row showed a value the server had
 * refused and a later reload silently lost it.
 *
 * Core principle 2 — never a lie that something succeeded — which #195/#282
 * fixed on the API while this layer kept reporting success. Those changes made
 * it MORE reachable, not less: the routes now return a typed 422 for fields
 * they previously accepted at 200.
 *
 * ## Driven through the component, not the helper
 *
 * `describeSaveError` is a pure function and testing it would prove nothing
 * about whether anything calls it. Three times in this branch family a test
 * pinned the unit and not the wiring, so this renders the real component,
 * makes a real edit, rejects the real client call, and asserts on what the
 * client would see. Deleting the revert or the report turns it red.
 */
vi.mock("@/lib/zt/client", () => ({
  ZtProxyError: class extends Error {},
  fetchCatalog: vi.fn(),
  fetchSelfAssessment: vi.fn(),
  patchSelfAssessmentAnswer: vi.fn(),
  submitSelfAssessment: vi.fn(),
}));

const CATALOG: ZtCatalog = {
  framework: "cisa_ztmm_2_0",
  pillars: [
    {
      code: "ID",
      name: "Identity",
      purpose: "Who is asking.",
      capabilities: [
        {
          code: "CISA.ID.01",
          pillar_code: "ID",
          name: "Authentication",
          outcome: "Phishing-resistant MFA.",
        },
      ],
    },
  ],
  stages: [
    { stage: 1, label: "Traditional", description: "" },
    { stage: 2, label: "Initial", description: "" },
    { stage: 3, label: "Advanced", description: "" },
    { stage: 4, label: "Optimal", description: "" },
  ],
  total_capabilities: 1,
};

function assessment(notes: string | null): ZtAssessment {
  return {
    id: "a1",
    service_id: "s1",
    framework: "cisa_ztmm_2_0",
    version: 1,
    status: "draft",
    approved_at: null,
    approved_by: null,
    answers: [
      {
        id: "ans1",
        assessment_id: "a1",
        capability_code: "CISA.ID.01",
        maturity_stage: 2,
        target_stage: null,
        notes,
        evidence_artifact_id: null,
        locked: false,
        answered_by: null,
        answered_at: null,
      },
    ],
    client_target_stage: 3,
  } as ZtAssessment;
}

describe("ZtSelfAssessment — a save that fails", () => {
  beforeEach(() => {
    vi.mocked(ztClient.fetchCatalog).mockResolvedValue(CATALOG);
    vi.mocked(ztClient.fetchSelfAssessment).mockResolvedValue(
      assessment("original"),
    );
    vi.mocked(ztClient.patchSelfAssessmentAnswer).mockReset();
  });

  async function editNotes(value: string): Promise<void> {
    render(<ZtSelfAssessment serviceId="s1" framework="cisa_ztmm_2_0" />);
    const notes = await screen.findByLabelText("Notes for CISA.ID.01");
    fireEvent.blur(notes, { target: { value } });
  }

  it("tells the client, rather than showing the change as saved", async () => {
    vi.mocked(ztClient.patchSelfAssessmentAnswer).mockRejectedValue(
      new Error("This endpoint applies only ['maturity_stage', 'notes']."),
    );

    await editNotes("a note the server will refuse");

    // The discriminating assertion. Before #283 this was silence: no alert, and
    // the rejected value left on screen as though it had been accepted.
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("That change was not saved.");
    expect(alert).toHaveTextContent("previous answer has been restored");
  });

  it("carries the server's own reason through, where there is one", async () => {
    // A generic sentence is an acceptable fallback; DISCARDING a typed reason
    // the API went to the trouble of returning is not.
    vi.mocked(ztClient.patchSelfAssessmentAnswer).mockRejectedValue(
      new Error("target_stage is not settable here"),
    );

    await editNotes("another note");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("target_stage is not settable here");
  });

  it("says nothing when the save succeeds", async () => {
    // The positive control. Without it, rendering the alert unconditionally
    // would satisfy both tests above.
    vi.mocked(ztClient.patchSelfAssessmentAnswer).mockResolvedValue(
      assessment("accepted").answers[0],
    );

    await editNotes("a note the server accepts");

    await waitFor(() =>
      expect(ztClient.patchSelfAssessmentAnswer).toHaveBeenCalled(),
    );
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
