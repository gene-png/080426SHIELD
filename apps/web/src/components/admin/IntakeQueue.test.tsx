import "@testing-library/jest-dom/vitest";

import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { IntakeQueue } from "./IntakeQueue";

import type { ClientProfileResponse } from "@/lib/intake/types";

/**
 * This surface had NO test file at all, and D-080 put a live guard on it.
 *
 * `hasIntake` used to compare against the `"(pending intake)"` sentinel, which
 * nothing wrote — so the gate on the Organization card was dead and the card
 * always rendered. Making the condition real (`legal_name IS NULL`) made that
 * gate fire for the first time, on a page with no coverage on either surface:
 * no vitest here, and no e2e spec matches "No client intake yet".
 *
 * The question these tests ask is the one the gate gets wrong when it is
 * enumerated rather than derived: **does the page claim there is no intake data
 * while holding some?** `Step2Organization` saves every field independently on
 * blur, so any single field can arrive alone.
 */

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/admin/client", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  fetchIntakeQueue: vi.fn(),
  fulfillServiceRequest: vi.fn(),
}));
vi.mock("@/lib/stages/client", () => ({
  useServiceStages: () => ({ phase: "ready", stages: [], reload: vi.fn() }),
}));

const { fetchIntakeQueue } = await import("@/lib/admin/client");
const mockFetch = vi.mocked(fetchIntakeQueue);

function client(over: Partial<ClientProfileResponse>): ClientProfileResponse {
  return {
    id: "00000000-0000-4000-8000-000000000001",
    legal_name: null,
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
    service_interests: null,
    ...over,
  } as ClientProfileResponse;
}

function queue(c: ClientProfileResponse | null) {
  mockFetch.mockResolvedValue({
    client: c,
    intake_completed_at: null,
    service_requests: [],
    artifacts: [],
    total_users: 1,
  } as never);
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("IntakeQueue — does the page deny data it is holding?", () => {
  // One case per field the Organization card renders. Three of these —
  // address_line2, state, postal_code — were in the card and NOT in the first
  // version of the predicate, so each produced "No client intake yet" printed
  // over a value the card would have shown. Derived from the rendered set, so
  // adding a field to the card without adding it here is the failure this
  // table exists to make loud.
  const fields: Array<[string, Partial<ClientProfileResponse>]> = [
    ["dba_name", { dba_name: "Atlas" }],
    ["website", { website: "https://atlas.example" }],
    ["size_band", { size_band: "500-1000" }],
    ["industry", { industry: "Defense" }],
    ["address_line1", { address_line1: "1 Harbour Way" }],
    ["address_line2", { address_line2: "Suite 400" }],
    ["city", { city: "Arlington" }],
    ["state", { state: "VA" }],
    ["postal_code", { postal_code: "22209" }],
    ["country", { country: "United States" }],
    ["prompting_context", { prompting_context: "Two data centres." }],
    ["service_interests", { service_interests: ["nist_csf"] }],
  ];

  it.each(fields)(
    "shows the Organization card when only %s is set",
    async (_label, over) => {
      queue(client(over));
      render(<IntakeQueue clientId="c1" />);

      // Positive state FIRST: wait for the card, then assert the denial is
      // absent. `toHaveCount(0)` on a page still fetching passes vacuously.
      expect(
        await screen.findByRole("heading", { name: "Organization" }),
      ).toBeInTheDocument();
      expect(screen.queryByText("No client intake yet")).toBeNull();
    },
  );

  it("still says there is no intake when the client really is empty", async () => {
    // The other half of the branch. Without this, a predicate hardwired to
    // `true` would satisfy every case above and the table would prove nothing.
    queue(client({}));
    render(<IntakeQueue clientId="c1" />);

    await waitFor(() =>
      expect(screen.getByText("No client intake yet")).toBeInTheDocument(),
    );
    expect(screen.queryByRole("heading", { name: "Organization" })).toBeNull();
  });

  it("does not count a whitespace-only field as intake data", async () => {
    // `hasContext` trims and the first version of this predicate did not, so a
    // website of "   " showed "In progress — not yet submitted" over nothing.
    queue(client({ website: "   " }));
    render(<IntakeQueue clientId="c1" />);

    await waitFor(() =>
      expect(screen.getByText("No client intake yet")).toBeInTheDocument(),
    );
  });

  it("titles the page with the org name only once it has one", async () => {
    // `hasName` and `hasIntakeData` are deliberately different questions:
    // what to CALL the org, versus whether there is anything to SHOW.
    queue(client({ state: "VA" }));
    render(<IntakeQueue clientId="c1" />);

    expect(
      await screen.findByRole("heading", { name: "Intake queue", level: 1 }),
    ).toBeInTheDocument();
    // …and the card is there anyway, which is the whole point of the split.
    expect(
      screen.getByRole("heading", { name: "Organization" }),
    ).toBeInTheDocument();
  });

  it("uses the client's name as the page title once one is set", async () => {
    queue(client({ legal_name: "Atlas Defense Solutions" }));
    render(<IntakeQueue clientId="c1" />);

    expect(
      await screen.findByRole("heading", {
        name: "Atlas Defense Solutions",
        level: 1,
      }),
    ).toBeInTheDocument();
  });
});
