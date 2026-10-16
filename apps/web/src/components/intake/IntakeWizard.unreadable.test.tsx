import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { IntakeWizard } from "./IntakeWizard";

/**
 * #1213, through the rendered wizard with the REAL intake client and `fetch`
 * stubbed: Submit answered by a 2xx we cannot read (a captive portal's page,
 * not our proxy) says the outcome is unknown, never "Failed to submit
 * intake." and never submitted.
 */

const SUBMIT_URL = "/api/proxy/intake/submit?client_id=client-1213";

vi.mock("next-auth/react", () => ({
  useSession: () => ({ data: { user: { email: "c@example.com" } } }),
}));
vi.mock("@/lib/intake/artifacts", () => ({
  listArtifacts: vi.fn(async () => ({ items: [] })),
}));
vi.mock("./Dropzone", () => ({
  Dropzone: () => null,
  EmptyArtifactsHint: () => null,
}));
vi.mock("./RedactionDisclosure", () => ({ RedactionDisclosure: () => null }));

const OUTCOME_UNKNOWN =
  "We couldn't confirm whether this finished. It may still complete; check before trying again.";

const STATE = {
  client: {
    id: "client-1213",
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
};

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      // #1262 (on main since #1335): submit names the client the wizard loaded.
      if (url === SUBMIT_URL && init?.method === "POST") {
        return new Response("<html>Sign in to the network</html>", {
          status: 200,
        });
      }
      if (url === "/api/proxy/intake" && !init?.method) {
        return new Response(JSON.stringify(STATE), { status: 200 });
      }
      throw new Error(`unexpected fetch ${init?.method ?? "GET"} ${url}`);
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function next(times = 1): Promise<void> {
  for (let i = 0; i < times; i += 1) {
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Next →" }));
    });
  }
}

describe("IntakeWizard: Submit answered by a 2xx we cannot read (#1213)", () => {
  it("says the outcome is unknown, not that it failed or succeeded", async () => {
    render(<IntakeWizard />);
    await screen.findByRole("button", { name: "Next →" });
    await next(5); // -> organization, contact, systems, notes, review
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Submit intake/ }));
    });
    // The submit really went out, so what follows is about its answer.
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      SUBMIT_URL,
      expect.objectContaining({ method: "POST" }),
    );
    expect(await screen.findByText(OUTCOME_UNKNOWN)).toBeVisible();
    expect(screen.queryByText("Failed to submit intake.")).toBeNull();
  });
});
