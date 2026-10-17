import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Step5Notes } from "./Step5Notes";
import type {
  IntakeStateResponse,
  ServiceRequestInput,
  ServiceType,
} from "@/lib/intake/types";

/**
 * #1223, review of 8a60a50a: Step 5 loads the same upload list as Step 6 and
 * let #550's "We couldn't confirm whether this finished..." through on a READ,
 * which changed nothing. It now uses `readFailureReason` (RR-2), as Step 6
 * does. Through the real `listArtifacts` with `fetch` stubbed.
 */

// The REAL empty-list hint (review of 3ffc5976): a mocked one hid that it
// rendered over a failed load. Only the upload control is stubbed.
vi.mock("../Dropzone", async (importActual) => ({
  ...(await importActual<typeof import("../Dropzone")>()),
  Dropzone: () => null,
}));
vi.mock("../RedactionDisclosure", () => ({ RedactionDisclosure: () => null }));

function respond(status: number, body: string): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(body, { status })),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Step5Notes: the uploads list failed to load (#1223)", () => {
  it("keeps #550's outcome sentence off this read, and shows its own copy", async () => {
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
    render(
      <Step5Notes
        state={
          {
            client: { service_interests: [] },
          } as unknown as IntakeStateResponse
        }
        serviceInputs={{} as Record<ServiceType, ServiceRequestInput>}
        onChange={vi.fn()}
      />,
    );
    expect(await screen.findByText("Failed to load uploads.")).toBeVisible();
    expect(screen.queryByText(/couldn't confirm/)).toBeNull();
    expect(screen.queryByText(/No documents uploaded/)).toBeNull();
  });

  it.each([
    ["a bare 500", 500, ""],
    ["a 200 with no item list", 200, JSON.stringify({})],
  ])("never says nothing was uploaded over %s", async (_n, status, body) => {
    respond(status, body);
    renderStep();
    expect(await screen.findByText("Failed to load uploads.")).toBeVisible();
    expect(screen.queryByText(/No documents uploaded/)).toBeNull();
  });

  it("shows a TYPED server sentence, and its own copy for untyped text (#1225)", async () => {
    respond(
      401,
      JSON.stringify({
        error: {
          code: 401,
          reason: "credentials_changed",
          message: "This session has ended. Sign in again.",
        },
      }),
    );
    const { unmount } = renderStep();
    expect(
      await screen.findByText("This session has ended. Sign in again."),
    ).toBeVisible();
    unmount();

    respond(
      403,
      JSON.stringify({
        error: {
          code: 403,
          message: "Client-role user is not bound to a client.",
        },
      }),
    );
    renderStep();
    expect(await screen.findByText("Failed to load uploads.")).toBeVisible();
    expect(screen.queryByText(/not bound to a client/)).toBeNull();
  });

  it("still says nothing was uploaded when the list loads empty", async () => {
    respond(200, JSON.stringify({ items: [] }));
    renderStep();
    expect(await screen.findByText(/No documents uploaded/)).toBeVisible();
    expect(screen.queryByText("Failed to load uploads.")).toBeNull();
  });
});

function renderStep() {
  return render(
    <Step5Notes
      state={
        { client: { service_interests: [] } } as unknown as IntakeStateResponse
      }
      serviceInputs={{} as Record<ServiceType, ServiceRequestInput>}
      onChange={vi.fn()}
    />,
  );
}
