import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Step6Review } from "./Step6Review";
import type {
  IntakeStateResponse,
  ServiceRequestInput,
  ServiceType,
} from "@/lib/intake/types";

/**
 * #1223 item 1: the review step lists the client's uploads so they can
 * confirm the attachment made it. A FAILED list used to render as an empty
 * one, "No documents uploaded. You can still submit", which is a false
 * statement about their own uploads. It now says the list did not load, in
 * the copy Step 5 already uses for the same failure. Through the real
 * `listArtifacts` with `fetch` stubbed.
 */

function respond(status: number, body: string): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(body, { status })),
  );
}

function renderStep() {
  render(
    <Step6Review
      state={
        {
          client: { legal_name: "Atlas Federal LLC", service_interests: [] },
          service_requests: [],
          intake_completed_at: null,
          contact: null,
        } as unknown as IntakeStateResponse
      }
      serviceInputs={{} as Record<ServiceType, ServiceRequestInput>}
      submitting={false}
      savesInFlight={0}
      submitError={null}
      alreadySubmittedAt={null}
      onSubmit={() => undefined}
    />,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Step6Review: the uploads list failed to load (#1223)", () => {
  it.each([
    ["a bare 500", 500, ""],
    ["an unreadable 2xx", 200, "<html>Sign in to the network</html>"],
  ])(
    "says so on %s, and never says nothing was uploaded",
    async (_n, status, body) => {
      respond(status, body);
      renderStep();
      expect(await screen.findByText("Failed to load uploads.")).toBeVisible();
      expect(screen.queryByText(/No documents uploaded/)).toBeNull();
    },
  );

  it("shows the server's own sentence when it sent one", async () => {
    respond(
      503,
      JSON.stringify({ error: { code: 503, message: "Storage is offline." } }),
    );
    renderStep();
    expect(await screen.findByText("Storage is offline.")).toBeVisible();
    expect(screen.queryByText(/No documents uploaded/)).toBeNull();
  });

  it("still says nothing was uploaded when the list loads empty", async () => {
    respond(200, JSON.stringify({ items: [] }));
    renderStep();
    expect(await screen.findByText(/No documents uploaded/)).toBeVisible();
    expect(screen.queryByText("Failed to load uploads.")).toBeNull();
  });
});
