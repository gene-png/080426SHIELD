import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as techDebtClient from "@/lib/tech_debt/client";
import type { Deliverable } from "@/lib/tech_debt/types";

import { DeliverableCard, type DeliverablePart } from "./DeliverableCard";

vi.mock("@/lib/tech_debt/client", () => ({
  finalizeDeliverable: vi.fn(),
  releaseDeliverable: vi.fn(),
  TechDebtProxyError: class extends Error {},
}));

/**
 * #1376: the card split across three sections. Each part shows only its own
 * controls, and the controls it does show work as they did in the whole card.
 */
function deliverable(overrides: Partial<Deliverable> = {}): Deliverable {
  return {
    id: "d1",
    service_id: "s1",
    title: "Tech Debt v1",
    summary: "1 finding",
    version: 1,
    pdf_artifact_id: "pdf-1",
    xlsx_artifact_id: null,
    pdf_filename: "report.pdf",
    xlsx_filename: null,
    finalized_at: "2026-08-17T00:00:00Z",
    released_at: null,
    ...overrides,
  } as Deliverable;
}

function renderPart(part: DeliverablePart, d: Deliverable | null): void {
  render(
    <DeliverableCard
      serviceId="s1"
      capabilityListStatus="approved"
      deliverable={d}
      onChange={vi.fn()}
      part={part}
    />,
  );
}

const finalize = () =>
  screen.queryByRole("button", { name: /^(Finalize|Re-finalize)$/ });
const release = () =>
  screen.queryByRole("button", { name: "Release to client" });
const preview = () => screen.queryByRole("link", { name: /View dashboard/ });
const download = () => screen.queryByRole("link", { name: "report.pdf" });

describe("DeliverableCard parts (#1376)", () => {
  it("generate: finalize and the downloads, no preview, no release", () => {
    renderPart("generate", deliverable());
    expect(finalize()).toBeEnabled();
    expect(download()).not.toBeNull();
    expect(preview()).toBeNull();
    expect(release()).toBeNull();
  });

  it("preview: the dashboard link only", () => {
    renderPart("preview", deliverable());
    expect(preview()).toHaveAttribute("href", "/dashboards/tech-debt/s1");
    expect(finalize()).toBeNull();
    expect(download()).toBeNull();
    expect(release()).toBeNull();
  });

  it("preview with nothing finalized says where to finalize", () => {
    renderPart("preview", null);
    expect(preview()).toBeNull();
    expect(
      screen.getByText(
        "Finalize the deliverable in Generate to preview what the client will see.",
      ),
    ).toBeVisible();
  });

  it("release: release only, under its own title", () => {
    renderPart("release", deliverable());
    expect(
      screen.getByText("Release to the client", { selector: "h3, h2, div, p" }),
    ).toBeVisible();
    expect(release()).toBeEnabled();
    expect(finalize()).toBeNull();
    expect(download()).toBeNull();
    expect(preview()).toBeNull();
  });

  it("release keeps its confirm, and calls the same release", async () => {
    const releaseDeliverable = vi.mocked(techDebtClient.releaseDeliverable);
    releaseDeliverable.mockResolvedValue(
      deliverable({ released_at: "2026-10-12T10:00:00Z" }),
    );
    renderPart("release", deliverable());
    fireEvent.click(release()!);
    expect(screen.getByText("Release v1 to the client?")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Yes, release" }));
    await waitFor(() => expect(releaseDeliverable).toHaveBeenCalledWith("d1"));
  });

  it("release with nothing finalized says where to finalize", () => {
    renderPart("release", null);
    expect(release()).toBeNull();
    expect(
      screen.getByText(
        "Finalize the deliverable in Generate before releasing it.",
      ),
    ).toBeVisible();
  });

  it("no part: the whole card, as before", () => {
    render(
      <DeliverableCard
        serviceId="s1"
        capabilityListStatus="approved"
        deliverable={deliverable()}
        onChange={vi.fn()}
      />,
    );
    expect(finalize()).not.toBeNull();
    expect(download()).not.toBeNull();
    expect(preview()).not.toBeNull();
    expect(release()).not.toBeNull();
  });
});
