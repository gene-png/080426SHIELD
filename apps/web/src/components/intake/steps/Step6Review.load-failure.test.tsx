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
 * statement about their own uploads. It now says the list did not load. Through the real
 * `listArtifacts` with `fetch` stubbed.
 *
 * #1225 item 2: Step 6's own copy for that failure, approved on #736
 * (6216024281). It says the list did not load, not that the uploads failed,
 * and keeps the "you can still submit" the empty state carries, which is
 * true: Submit does not wait on this list.
 */

const LIST_FAILED =
  "We couldn't load your uploaded documents. Your uploads are not affected, and you can still submit.";

function respond(status: number, body: string): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(body, { status })),
  );
}

function renderStep(serviceInterests: ServiceType[] = []) {
  render(
    <Step6Review
      state={
        {
          client: {
            legal_name: "Atlas Federal LLC",
            service_interests: serviceInterests,
          },
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
      expect(await screen.findByText(LIST_FAILED)).toBeVisible();
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

  it("keeps #550's outcome sentence off this read (RR-2), and shows its own copy", async () => {
    // A read changed nothing, so "check before trying again" does not apply.
    respond(
      504,
      JSON.stringify({
        error: {
          code: 504,
          reason: "upstream_outcome_unknown",
          message:
            "We couldn't confirm whether this finished. It may still complete; check before trying again.",
        },
      }),
    );
    renderStep();
    expect(await screen.findByText(LIST_FAILED)).toBeVisible();
    expect(screen.queryByText(/couldn't confirm/)).toBeNull();
  });

  it("treats a 200 with no item list as a failed load, not an empty one", async () => {
    respond(200, JSON.stringify({}));
    renderStep();
    expect(await screen.findByText(LIST_FAILED)).toBeVisible();
    expect(screen.queryByText(/No documents uploaded/)).toBeNull();
  });

  it("keeps Submit enabled while the list has failed (#1225)", async () => {
    respond(500, "");
    renderStep(["tech_debt"]);
    expect(await screen.findByText(LIST_FAILED)).toBeVisible();
    expect(screen.getByRole("button", { name: /Submit intake/ })).toBeEnabled();
  });

  it("still says nothing was uploaded when the list loads empty", async () => {
    respond(200, JSON.stringify({ items: [] }));
    renderStep();
    expect(await screen.findByText(/No documents uploaded/)).toBeVisible();
    expect(screen.queryByText(LIST_FAILED)).toBeNull();
  });
});
