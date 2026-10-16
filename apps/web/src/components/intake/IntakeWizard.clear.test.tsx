import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as intakeClient from "@/lib/intake/client";
import type {
  IntakePatchRequest,
  IntakeStateResponse,
  IntakeSubmitRequest,
} from "@/lib/intake/types";

import { IntakeWizard } from "./IntakeWizard";

/**
 * #1093 item 1, through the rendered wizard (review of d23c4ef6).
 *
 * - A field the client CLEARED is submitted as null. The review shows an
 *   emptied field as not provided, so if its blur save never landed, Submit
 *   is what has to carry the clear; `?? undefined` turned the null back into
 *   a dropped key and the server kept the old value.
 * - Step 4's systems text, emptied, is saved as null, the same fix as Step 2.
 */

vi.mock("next-auth/react", () => ({
  useSession: () => ({ data: { user: { email: "c@example.com" } } }),
}));
vi.mock("@/lib/intake/client", () => ({
  ProxyError: class ProxyError extends Error {},
  fetchIntake: vi.fn(),
  patchIntake: vi.fn(),
  submitIntake: vi.fn(),
}));
vi.mock("@/lib/intake/artifacts", () => ({
  listArtifacts: vi.fn(async () => ({ items: [] })),
}));
vi.mock("./Dropzone", () => ({
  Dropzone: () => null,
  EmptyArtifactsHint: () => null,
}));
vi.mock("./RedactionDisclosure", () => ({ RedactionDisclosure: () => null }));

const patchIntake = vi.mocked(intakeClient.patchIntake);
const submitIntake = vi.mocked(intakeClient.submitIntake);

function serverState(): IntakeStateResponse {
  return {
    client: {
      id: "client-1093",
      legal_name: "Atlas Federal LLC",
      dba_name: null,
      website: "https://atlas.example/",
      size_band: null,
      industry: null,
      address_line1: null,
      address_line2: null,
      city: "Arlington",
      state: null,
      postal_code: null,
      country: null,
      prompting_context: "Two systems in scope.",
      service_interests: ["tech_debt"],
      intake_completed_at: null,
    },
    service_requests: [],
    intake_completed_at: null,
    contact: null,
  } as IntakeStateResponse;
}

beforeEach(() => {
  vi.mocked(intakeClient.fetchIntake).mockResolvedValue(serverState());
  patchIntake.mockReset();
  submitIntake.mockReset();
  submitIntake.mockResolvedValue(serverState());
});

async function next(times = 1): Promise<void> {
  for (let i = 0; i < times; i += 1) {
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Next →" }));
    });
  }
}

async function empty(id: string): Promise<void> {
  const field = document.getElementById(id) as HTMLInputElement;
  expect(field, `no #${id} on this step`).not.toBeNull();
  expect(field.value, `setup: #${id} must start filled`).not.toBe("");
  await act(async () => {
    fireEvent.change(field, { target: { value: "" } });
    fireEvent.blur(field, { target: { value: "" } });
  });
}

function submitted(): IntakeSubmitRequest {
  expect(submitIntake).toHaveBeenCalledTimes(1);
  return submitIntake.mock.calls[0][0] as IntakeSubmitRequest;
}

describe("IntakeWizard: a cleared field (#1093)", () => {
  it("submits a cleared field as null when its save never landed, and leaves the others as they were", async () => {
    patchIntake.mockRejectedValue(new TypeError("Failed to fetch"));
    render(<IntakeWizard />);
    await screen.findByRole("button", { name: "Next →" });
    await next(); // -> organization
    await empty("website");
    expect(patchIntake.mock.calls.map((c) => c[0])).toEqual([
      { client: { website: null } } satisfies IntakePatchRequest,
    ]);
    await next(4); // -> contact, systems, notes, review
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Submit intake/ }));
    });
    const client = submitted().client;
    expect(client?.website).toBeNull();
    // A field the server already holds is sent as held; one it holds as
    // NULL and nobody cleared is left out, as before.
    expect(client?.city).toBe("Arlington");
    expect(client?.dba_name).toBeUndefined();
  });

  it("saves Step 4's emptied systems text as null", async () => {
    patchIntake.mockResolvedValue(serverState());
    render(<IntakeWizard />);
    await screen.findByRole("button", { name: "Next →" });
    await next(3); // -> organization, contact, systems
    await empty("prompting_context");
    expect(patchIntake.mock.calls.map((c) => c[0])).toEqual([
      { client: { prompting_context: null } } satisfies IntakePatchRequest,
    ]);
  });
});
