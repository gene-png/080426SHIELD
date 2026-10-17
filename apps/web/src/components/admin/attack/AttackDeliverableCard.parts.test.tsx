import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { AttackDeliverable } from "@/lib/attack/types";

import { AttackDeliverableCard } from "./AttackDeliverableCard";

/**
 * #1377: the card shows one section's controls. Generate is Finalize and the
 * downloads, Quality check is the dashboard link, Approve and release is
 * Release behind its confirm. Absent a part, the whole card, as before.
 * Control names are the card's own labels, typed here.
 */

vi.mock("@/lib/attack/client", () => ({
  AttackProxyError: class extends Error {},
  finalizeAttackDeliverable: vi.fn(),
  releaseAttackDeliverable: vi.fn(),
}));

function finalized(): AttackDeliverable {
  return {
    id: "d1",
    version: 1,
    finalized_at: "2026-10-17T12:00:00Z",
    released_at: null,
    pdf_artifact_id: "pdf1",
    pdf_filename: "report.pdf",
    xlsx_artifact_id: "xlsx1",
    xlsx_filename: "report.xlsx",
  } as unknown as AttackDeliverable;
}

function card(
  part: "generate" | "preview" | "release" | undefined,
  deliverable: AttackDeliverable | null,
) {
  return render(
    <AttackDeliverableCard
      serviceId="svc-1"
      assessmentStatus="approved"
      deliverable={deliverable}
      onChange={() => undefined}
      part={part}
    />,
  );
}

const finalize = () => screen.queryByRole("button", { name: "Re-finalize" });
const release = () =>
  screen.queryByRole("button", { name: "Release to client" });
const dashboard = () => screen.queryByRole("link", { name: /View dashboard/ });
const download = () => screen.queryByRole("link", { name: "report.pdf" });

describe("AttackDeliverableCard parts (#1377)", () => {
  it("generate: Finalize and the downloads, no Release, no dashboard link", () => {
    card("generate", finalized());
    expect(finalize()).toBeInTheDocument();
    expect(download()).toBeInTheDocument();
    expect(release()).toBeNull();
    expect(dashboard()).toBeNull();
  });

  it("preview: the dashboard link only", () => {
    card("preview", finalized());
    expect(dashboard()).toBeInTheDocument();
    expect(finalize()).toBeNull();
    expect(release()).toBeNull();
    expect(download()).toBeNull();
  });

  it("release: Release only, no Finalize, no downloads, no dashboard link", () => {
    card("release", finalized());
    expect(release()).toBeInTheDocument();
    expect(finalize()).toBeNull();
    expect(download()).toBeNull();
    expect(dashboard()).toBeNull();
  });

  it("no part: the whole card, as before", () => {
    card(undefined, finalized());
    expect(finalize()).toBeInTheDocument();
    expect(release()).toBeInTheDocument();
    expect(dashboard()).toBeInTheDocument();
    expect(download()).toBeInTheDocument();
  });

  it("preview with nothing finalized says so and shows no card", () => {
    card("preview", null);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.queryByRole("link")).toBeNull();
    expect(
      screen.getByText(/Finalize the deliverable in Generate/),
    ).toBeVisible();
  });

  it("release with nothing finalized offers nothing to release", () => {
    card("release", null);
    expect(release()).toBeNull();
    expect(finalize()).toBeNull();
    expect(screen.queryByRole("button", { name: "Finalize" })).toBeNull();
    expect(
      screen.getByText(/Finalize the deliverable in Generate/),
    ).toBeVisible();
  });
});
