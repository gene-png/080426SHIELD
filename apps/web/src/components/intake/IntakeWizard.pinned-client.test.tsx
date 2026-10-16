import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { IntakeStateResponse } from "@/lib/intake/types";

import { IntakeWizard } from "./IntakeWizard";

/**
 * #1262, the `/intake` residual (answered on #1262, 6219252390). An admin's
 * `/intake` carries no client of its own, so every write fell back to the
 * shared active-client cookie at REQUEST time. Another tab opening a
 * workspace for client B rewrote that cookie, and the wizard still showing A
 * then filed uploads, saved fields and submitted under B.
 *
 * The wizard now names the client it LOADED on every later call. Driven
 * through the real `lib/intake` wrappers with `fetch` stubbed, so what is
 * asserted is the URL each call actually sends.
 */

vi.mock("next-auth/react", () => ({
  useSession: () => ({ data: { user: { email: "admin@example.com" } } }),
}));
vi.mock("./RedactionDisclosure", () => ({ RedactionDisclosure: () => null }));
// The upload itself is pinned by its own prop; the drop gesture is not what
// this file tests.
const dropzoneProps: Array<{ clientId?: string }> = [];
vi.mock("./Dropzone", () => ({
  Dropzone: (props: { clientId?: string }) => {
    dropzoneProps.push(props);
    return null;
  },
  EmptyArtifactsHint: () => null,
}));

const CLIENT_A = "00000000-0000-4000-8000-0000000000a1";

function stateFor(id: string): IntakeStateResponse {
  return {
    client: {
      id,
      legal_name: "Client A LLC",
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
  } as unknown as IntakeStateResponse;
}

const calls: Array<{ method: string; url: string }> = [];

beforeEach(() => {
  calls.length = 0;
  dropzoneProps.length = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ method: init?.method ?? "GET", url });
      if (url.startsWith("/api/proxy/artifacts")) {
        return new Response(JSON.stringify({ items: [] }), { status: 200 });
      }
      return new Response(JSON.stringify(stateFor(CLIENT_A)), { status: 200 });
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

const PINNED = `client_id=${CLIENT_A}`;

describe("IntakeWizard names the client it loaded on every later call (#1262)", () => {
  it("saves a field under the loaded client", async () => {
    render(<IntakeWizard />);
    await screen.findByRole("button", { name: "Next →" });
    await next(); // -> organization
    const city = document.getElementById("city") as HTMLInputElement;
    await act(async () => {
      fireEvent.change(city, { target: { value: "Arlington" } });
      fireEvent.blur(city, { target: { value: "Arlington" } });
    });
    const patches = calls.filter((c) => c.method === "PATCH");
    expect(patches.length).toBeGreaterThan(0);
    for (const p of patches) expect(p.url).toBe(`/api/proxy/intake?${PINNED}`);
  });

  it("lists, uploads and submits under the loaded client", async () => {
    render(<IntakeWizard />);
    await screen.findByRole("button", { name: "Next →" });
    await next(4); // -> organization, contact, systems, notes
    expect(dropzoneProps.length).toBeGreaterThan(0);
    expect(dropzoneProps.at(-1)?.clientId).toBe(CLIENT_A);
    await next(); // -> review
    const submit = await screen.findByRole("button", { name: /Submit intake/ });
    await act(async () => {
      fireEvent.click(submit);
    });

    const lists = calls.filter(
      (c) => c.method === "GET" && c.url.startsWith("/api/proxy/artifacts"),
    );
    // Step 5's read and Step 6's read.
    expect(lists.length).toBeGreaterThanOrEqual(2);
    for (const l of lists) expect(l.url).toBe(`/api/proxy/artifacts?${PINNED}`);

    const submits = calls.filter((c) => c.method === "POST");
    expect(submits).toEqual([
      { method: "POST", url: `/api/proxy/intake/submit?${PINNED}` },
    ]);
  });

  it("loads the intake itself without naming a client, as before", async () => {
    render(<IntakeWizard />);
    await screen.findByRole("button", { name: "Next →" });
    expect(calls[0]).toEqual({ method: "GET", url: "/api/proxy/intake" });
  });
});
