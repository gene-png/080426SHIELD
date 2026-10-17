import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as intakeClient from "@/lib/intake/client";
import type { IntakeStateResponse } from "@/lib/intake/types";

import { IntakeWizard } from "./IntakeWizard";

/**
 * #1321: the session's name is `display_name ?? email`, so for an account with
 * no display_name it IS the email. Step 3's Full name input took it as the
 * default, and each input saves on blur, so tabbing through the step saved the
 * email as the account's name. An account with no display_name now shows an
 * empty Full name, and a blur saves nothing for it.
 */

vi.mock("next-auth/react", () => ({
  useSession: () => ({
    data: { user: { email: "pat@example.com", name: "pat@example.com" } },
  }),
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

const OWN = {
  display_name: null,
  email: "pat@example.com",
  title: "Own Title",
  phone: "555-0001",
  timezone: "America/Chicago",
  is_override: false,
};

function overriddenState(): IntakeStateResponse {
  return {
    client: {
      id: "client-1282",
      legal_name: "Atlas Federal LLC",
      service_interests: ["tech_debt"],
      primary_contact_name: "Dana Director",
      primary_contact_email: "dana@example.com",
      primary_contact_title: "Override Title",
      primary_contact_phone: "555-0199",
    },
    service_requests: [],
    intake_completed_at: null,
    contact: {
      display_name: "Dana Director",
      email: "dana@example.com",
      title: "Override Title",
      phone: "555-0199",
      timezone: "America/Chicago",
      is_override: true,
    },
    submitter: OWN,
  } as unknown as IntakeStateResponse;
}

beforeEach(() => {
  vi.mocked(intakeClient.fetchIntake).mockResolvedValue(overriddenState());
  vi.mocked(intakeClient.patchIntake).mockReset();
  vi.mocked(intakeClient.patchIntake).mockResolvedValue(overriddenState());
});

async function openContactStep(): Promise<void> {
  render(<IntakeWizard />);
  await screen.findByRole("button", { name: "Next →" });
  for (let i = 0; i < 2; i += 1) {
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Next →" }));
    });
  }
}

function input(id: string): HTMLInputElement {
  const el = document.getElementById(id) as HTMLInputElement | null;
  expect(el, `no #${id} on Step 3`).not.toBeNull();
  return el as HTMLInputElement;
}

describe("IntakeWizard Step 3 for an account with no display_name (#1321)", () => {
  it("leaves Full name empty rather than showing the email as the name", async () => {
    await openContactStep();
    expect(input("display_name").value).toBe("");
    // The rest of the account's own details still show.
    expect(input("title").value).toBe("Own Title");
  });

  it("saves no name when the inputs are tabbed through unchanged", async () => {
    await openContactStep();
    for (const id of ["display_name", "title", "phone", "timezone"]) {
      await act(async () => {
        fireEvent.blur(input(id));
      });
    }
    const calls = vi.mocked(intakeClient.patchIntake).mock.calls.map((c) => c[0]);
    // What must appear first: the blurs did save, so the check below is not
    // vacuous.
    expect(JSON.stringify(calls)).toContain("Own Title");
    expect(JSON.stringify(calls)).not.toContain("pat@example.com");
  });
});
