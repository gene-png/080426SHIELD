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
 * fixed on the API while this layer kept reporting success.
 *
 * A draft of this docstring said those changes made it "MORE reachable ... the
 * routes now return a typed 422 for fields they previously accepted at 200".
 * **That is false for these two components.** They only ever send
 * `{maturity_stage}` / `{maturity_tier}` and `{notes}` — exactly the fields
 * both narrowed schemas accept — so `extra="forbid"` cannot fire from this UI.
 *
 * The failures this surface CAN produce, which is what the cases below model:
 * a 409 (the consultant approved the assessment while the client was typing,
 * and the likeliest of these by far), `notes` over `max_length=8000`, an
 * expired session, and network loss.
 *
 * ## Driven through the component, not the helper
 *
 * `describe-save-error.test.ts` owns the message CONTENT and can be run
 * locally. This file owns the WIRING, which that one cannot see: whether
 * anything calls the helper, and whether the revert reaches the screen. Three
 * times in this branch family a test pinned the unit and not the wiring, so
 * this renders the real component, makes a real edit, rejects with the error
 * shape the real client throws, and asserts on what a client would see.
 *
 * Deleting the report turns it red; so, now, does deleting the revert — the
 * first draft asserted only on alert text and would have stayed green with the
 * entire recovery removed.
 */
/**
 * The error shape the real client throws — a `payload` and a `status`, NOT a
 * plain `Error`. A draft of this file rejected with `new Error("...")`, which
 * production cannot produce: `ZtProxyError`'s constructor is
 * `super(`ZT proxy ${status}`)` and the reason lives on `.payload`. The test
 * passed against a double and would have been 100% wrong live.
 */
function proxyError(status: number, payload: unknown): Error {
  return Object.assign(new Error(`ZT proxy ${status}`), { status, payload });
}

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
      proxyError(409, {
        detail: "Your self-assessment is no longer editable.",
      }),
    );

    await editNotes("a note the server will refuse");

    // Before #283 this was silence: no alert, and the rejected value left on
    // screen as though it had been accepted.
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("CISA.ID.01");
    expect(alert).toHaveTextContent("no longer editable");
  });

  it("puts the SERVER'S value back on screen, not a remembered one", async () => {
    // THE ASSERTION THE FIRST DRAFT LACKED. It checked only the alert text, so
    // deleting the entire revert left every test green — the #72 shape in the
    // file written to prevent it. The `<summary>` preview renders from state,
    // so it is observable in jsdom and goes red if the re-fetch is removed.
    vi.mocked(ztClient.patchSelfAssessmentAnswer).mockRejectedValue(
      proxyError(409, { detail: "locked" }),
    );
    vi.mocked(ztClient.fetchSelfAssessment)
      .mockResolvedValueOnce(assessment("original"))
      .mockResolvedValueOnce(assessment("what the server actually has"));

    await editNotes("a note the server will refuse");

    await screen.findByRole("alert");
    // Server truth, re-fetched — NOT the pre-write snapshot the client's
    // browser happened to be holding.
    expect(
      await screen.findByText(/what the server actually has/),
    ).toBeInTheDocument();
  });

  it("carries the server's own reason through, where there is one", async () => {
    // A generic sentence is an acceptable fallback; DISCARDING a typed reason
    // the API went to the trouble of returning is not.
    vi.mocked(ztClient.patchSelfAssessmentAnswer).mockRejectedValue(
      proxyError(422, {
        detail: [{ msg: "String should have at most 8000 characters" }],
      }),
    );

    await editNotes("another note");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("at most 8000 characters");
    // And never the internal string the proxy class puts in `.message`.
    expect(alert).not.toHaveTextContent("ZT proxy");
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
