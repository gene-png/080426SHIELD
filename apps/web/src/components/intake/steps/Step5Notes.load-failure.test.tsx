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

vi.mock("../Dropzone", () => ({
  Dropzone: () => null,
  EmptyArtifactsHint: () => null,
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
  });
});
