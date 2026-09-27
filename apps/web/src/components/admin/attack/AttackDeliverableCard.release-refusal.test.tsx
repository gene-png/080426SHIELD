/**
 * #622: the API refuses to release an ATT&CK assessment with a Not verified
 * row or a Partial with no reason, and the refusal must reach the consultant
 * as the API's own sentence -- it names the techniques -- not as a status code.
 */
import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { AttackDeliverable } from "@/lib/attack/types";

import { AttackDeliverableCard } from "./AttackDeliverableCard";

const MESSAGE =
  "Nothing was released: 1 technique is Not verified (T1595.001).";

vi.mock("@/lib/attack/client", () => {
  class AttackProxyError extends Error {
    constructor(
      public readonly status: number,
      public readonly payload: unknown,
    ) {
      super(`ATT&CK proxy ${status}`);
    }
  }
  return {
    AttackProxyError,
    finalizeAttackDeliverable: vi.fn(),
    releaseAttackDeliverable: vi.fn(async () => {
      throw new AttackProxyError(409, {
        error: {
          reason: "attack_not_release_ready",
          message:
            "Nothing was released: 1 technique is Not verified (T1595.001).",
        },
      });
    }),
  };
});

const UNRELEASED: AttackDeliverable = {
  id: "d1",
  service_id: "svc-1",
  title: "ATT&CK Coverage v1",
  summary: null,
  version: 1,
  pdf_artifact_id: null,
  xlsx_artifact_id: null,
  pdf_filename: null,
  xlsx_filename: null,
  finalized_at: "2026-09-24T00:00:00Z",
  finalized_by: null,
  released_at: null,
  superseded_by: null,
};

describe("AttackDeliverableCard, a release the API refuses (#622)", () => {
  it("shows the API's sentence naming what blocks the release", async () => {
    render(
      <AttackDeliverableCard
        serviceId="svc-1"
        assessmentStatus="approved"
        deliverable={UNRELEASED}
        onChange={() => undefined}
        catalogStale={false}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Release to client" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, release" }));
    expect(await screen.findByText(MESSAGE)).toBeInTheDocument();
  });
});
