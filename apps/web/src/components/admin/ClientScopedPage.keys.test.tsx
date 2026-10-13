import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as clientReads from "@/lib/admin/client-reads";

import { ClientScopedPage } from "./ClientScopedPage";

/**
 * RR-2 (for #1121): the picker and the page body are siblings, and each is
 * keyed by the chosen client so it re-mounts when the client changes. Keyed
 * by the bare id, the two siblings shared one key, and React warned
 * "Encountered two children with the same key" on every chosen render.
 */

vi.mock("next/navigation", () => ({
  usePathname: () => "/admin/risk-register",
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/lib/admin/client-reads", () => ({
  readClientList: vi.fn(),
  readActiveClient: vi.fn(),
}));

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ClientScopedPage keys", () => {
  it("renders a chosen client with no duplicate React key", async () => {
    const errors = vi.spyOn(console, "error").mockImplementation(() => {});
    vi.mocked(clientReads.readClientList).mockResolvedValue({
      clients: [
        {
          id: "c1",
          legal_name: "Atlas",
          dba_name: null,
          industry: null,
          size_band: null,
          intake_completed_at: null,
          created_at: "2026-10-01T00:00:00Z",
          archived_at: null,
          open_request_count: 0,
          total_request_count: 0,
        },
        {
          id: "c2",
          legal_name: "Beacon",
          dba_name: null,
          industry: null,
          size_band: null,
          intake_completed_at: null,
          created_at: "2026-10-02T00:00:00Z",
          archived_at: null,
          open_request_count: 0,
          total_request_count: 0,
        },
      ],
    });
    vi.mocked(clientReads.readActiveClient).mockResolvedValue({ active: "c1" });

    render(
      <ClientScopedPage
        header={(chosen) => (
          <h1>{chosen ? `Page for ${chosen.label}` : "Page"}</h1>
        )}
        noClient={<p>Pick a client first</p>}
      >
        {({ client }) => <p>Body for {client.label}</p>}
      </ClientScopedPage>,
    );

    // The positive state first: the chosen client's body rendered.
    expect(await screen.findByText("Body for Atlas")).toBeInTheDocument();
    const duplicates = errors.mock.calls.filter((call) =>
      String(call[0]).includes("Encountered two children with the same key"),
    );
    expect(duplicates).toEqual([]);
  });
});
