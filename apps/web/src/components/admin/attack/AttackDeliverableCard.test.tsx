/**
 * #556: finalize and release are refused by the API for an assessment scored
 * against another ATT&CK catalog, so the card does not offer them. Both halves
 * are asserted: stale disables, current does not, or a test that only checks
 * "disabled" would pass on a card that disabled everything.
 */
import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { AttackDeliverable } from "@/lib/attack/types";

import { AttackDeliverableCard } from "./AttackDeliverableCard";

vi.mock("@/lib/attack/client", () => ({
  AttackProxyError: class extends Error {},
  finalizeAttackDeliverable: vi.fn(),
  releaseAttackDeliverable: vi.fn(),
}));

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

function renderCard(catalogStale: boolean): void {
  render(
    <AttackDeliverableCard
      serviceId="svc-1"
      assessmentStatus="approved"
      deliverable={UNRELEASED}
      onChange={() => undefined}
      catalogStale={catalogStale}
    />,
  );
}

describe("AttackDeliverableCard, stale ATT&CK catalog (#556)", () => {
  it("offers neither finalize nor release", () => {
    renderCard(true);
    expect(screen.getByRole("button", { name: "Re-finalize" })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Release to client" }),
    ).toBeDisabled();
  });

  it("offers both on a current assessment", () => {
    renderCard(false);
    expect(
      screen.getByRole("button", { name: "Re-finalize" }),
    ).not.toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Release to client" }),
    ).not.toBeDisabled();
  });
});
