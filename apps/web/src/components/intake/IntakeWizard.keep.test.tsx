import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as intakeClient from "@/lib/intake/client";
import type { IntakeStateResponse } from "@/lib/intake/types";

import { IntakeWizard } from "./IntakeWizard";

/**
 * #1115, review of 8b4f28a1: "It is still in the form, so you can save it
 * again." (S-1115-1) is true only of the fields the wizard keeps, the ones it
 * submits (Step 2 and Step 4's). Step 3's are re-read from the server when the
 * step reopens, so an answer that did not judge them gets S-1115-2 instead.
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

const KEPT =
  "This value was not saved. It is still in the form, so you can save it again.";
const RETYPE = "This value was not saved. Set it again to save it.";

function serverState(): IntakeStateResponse {
  return {
    client: {
      id: "client-1115",
      legal_name: "Atlas Federal LLC",
      dba_name: null,
      website: null,
      size_band: null,
      industry: null,
      address_line1: null,
      address_line2: null,
      city: null,
      state: null,
      postal_code: null,
      country: null,
      prompting_context: null,
      service_interests: ["tech_debt"],
      intake_completed_at: null,
    },
    service_requests: [],
    intake_completed_at: null,
    contact: null,
  } as IntakeStateResponse;
}

/** An untyped 403 from in front of the api: it did not judge the value. */
function bare403(): Error {
  const ProxyError = intakeClient.ProxyError as unknown as new (
    m: string,
  ) => Error;
  return Object.assign(new ProxyError("Intake proxy 403"), {
    status: 403,
    payload: "",
  });
}

beforeEach(() => {
  vi.mocked(intakeClient.fetchIntake).mockResolvedValue(serverState());
  vi.mocked(intakeClient.patchIntake).mockReset();
  vi.mocked(intakeClient.patchIntake).mockRejectedValue(bare403());
});

async function next(times = 1): Promise<void> {
  for (let i = 0; i < times; i += 1) {
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Next →" }));
    });
  }
}

async function typeAndBlur(id: string, value: string): Promise<void> {
  const input = document.getElementById(id) as HTMLInputElement;
  expect(input, `no #${id} on this step`).not.toBeNull();
  await act(async () => {
    fireEvent.change(input, { target: { value } });
    fireEvent.blur(input, { target: { value } });
  });
}

describe("IntakeWizard: which fields the kept-value sentence may name (#1115)", () => {
  it("says a Step 2 value is still in the form", async () => {
    render(<IntakeWizard />);
    await screen.findByRole("button", { name: "Next →" });
    await next(); // -> organization
    await typeAndBlur("city", "Arlington");
    expect(screen.getByText(KEPT, { exact: false })).toBeVisible();
    expect(screen.queryByText(RETYPE, { exact: false })).toBeNull();
  });

  it("does not say a Step 3 contact override is still in the form", async () => {
    // Review of 74211b70: the override travels under `client`, so only
    // keepsPatch's every-key-is-submitted clause stands between it and the
    // kept sentence. Its fields re-read from the server when the step reopens.
    render(<IntakeWizard />);
    await screen.findByRole("button", { name: "Next →" });
    await next(2); // -> organization, contact
    await act(async () => {
      fireEvent.click(
        screen.getByRole("checkbox", { name: /I am not the primary contact/ }),
      );
    });
    await typeAndBlur("primary_contact_email", "pat@atlas.example");
    // #1262: every save now names the client the wizard loaded.
    expect(vi.mocked(intakeClient.patchIntake)).toHaveBeenLastCalledWith(
      { client: { primary_contact_email: "pat@atlas.example" } },
      "client-1115",
    );
    expect(screen.getByText(RETYPE, { exact: false })).toBeVisible();
    expect(screen.queryByText(KEPT, { exact: false })).toBeNull();
  });

  it("does not say a Step 3 value is still in the form", async () => {
    render(<IntakeWizard />);
    await screen.findByRole("button", { name: "Next →" });
    await next(2); // -> organization, contact
    await typeAndBlur("phone", "555-0100");
    expect(screen.getByText(RETYPE, { exact: false })).toBeVisible();
    expect(screen.queryByText(KEPT, { exact: false })).toBeNull();
  });
});
