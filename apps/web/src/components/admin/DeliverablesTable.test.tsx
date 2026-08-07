import "@testing-library/jest-dom/vitest";

import { render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DeliverablesTable } from "./DeliverablesTable";

import type { AdminDeliverableRow } from "@/lib/admin/deliverables";

/**
 * The table's job is to answer "what have we produced, and what has the client
 * actually seen?" — so the assertions that matter are the ones about
 * client-visibility and version grouping, not layout.
 */

vi.mock("@/lib/admin/deliverables", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  fetchAdminDeliverables: vi.fn(),
}));

vi.mock("@/lib/active-client", () => ({ getActiveClientId: vi.fn() }));

const { fetchAdminDeliverables } = await import("@/lib/admin/deliverables");
const mockFetch = vi.mocked(fetchAdminDeliverables);
const { getActiveClientId } = await import("@/lib/active-client");
const mockActiveClient = vi.mocked(getActiveClientId);

beforeEach(() => {
  // Every test below is about an admin who has already picked a tenant, unless
  // it says otherwise.
  mockActiveClient.mockResolvedValue("11111111-1111-4111-8111-111111111111");
});

afterEach(() => {
  vi.clearAllMocks();
});

function row(over: Partial<AdminDeliverableRow>): AdminDeliverableRow {
  return {
    id: "d1",
    service_id: "s1",
    service_kind: "nist_csf",
    service_title: "NIST CSF 2.0 Assessment",
    title: "Report",
    version: 1,
    status: "generated",
    client_visible: false,
    finalized_at: "2026-02-01T00:00:00Z",
    released_at: null,
    pdf_artifact_id: null,
    xlsx_artifact_id: null,
    docx_artifact_id: null,
    ...over,
  };
}

describe("DeliverablesTable", () => {
  it("shows unreleased deliverables — the reason the surface exists", async () => {
    mockFetch.mockResolvedValue({ items: [row({})] });
    render(<DeliverablesTable />);
    expect(await screen.findByText("Generated")).toBeInTheDocument();
    expect(screen.getByText("v1")).toBeInTheDocument();
  });

  it("counts only released rows as visible to the client", async () => {
    mockFetch.mockResolvedValue({
      items: [
        row({ id: "d3", version: 3, status: "released", client_visible: true }),
        row({ id: "d2", version: 2 }),
        row({ id: "d1", version: 1, status: "superseded" }),
      ],
    });
    render(<DeliverablesTable />);
    expect(
      await screen.findByText(/1 visible to the client/),
    ).toBeInTheDocument();
    expect(screen.getByText(/3 versions across 1 service/)).toBeInTheDocument();
  });

  it("groups every version of a service under one heading", async () => {
    mockFetch.mockResolvedValue({
      items: [
        row({
          id: "a2",
          service_id: "sA",
          service_title: "Service A",
          version: 2,
        }),
        row({
          id: "a1",
          service_id: "sA",
          service_title: "Service A",
          version: 1,
        }),
        row({
          id: "b1",
          service_id: "sB",
          service_title: "Service B",
          version: 1,
        }),
      ],
    });
    render(<DeliverablesTable />);
    const groupA = (
      await screen.findByRole("heading", { name: "Service A" })
    ).closest("div")?.parentElement as HTMLElement;
    expect(within(groupA).getAllByRole("row")).toHaveLength(3); // header + 2
    expect(
      screen.getByRole("heading", { name: "Service B" }),
    ).toBeInTheDocument();
  });

  it("surfaces a load failure instead of rendering an empty table", async () => {
    mockFetch.mockRejectedValue(new Error("Upstream exploded."));
    render(<DeliverablesTable />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Upstream exploded.");
    expect(screen.queryByText("No deliverables yet")).toBeNull();
  });

  it("shows the empty state only when the tenant genuinely has none", async () => {
    mockFetch.mockResolvedValue({ items: [] });
    render(<DeliverablesTable />);
    await waitFor(() =>
      expect(screen.getByText("No deliverables yet")).toBeInTheDocument(),
    );
  });

  // With no tenant chosen there is nothing to scope the request to, and the API
  // dependency answers a missing X-Client-Id with a 400. Asking anyway printed
  // "Failed to load deliverables (400)." — an upstream status dump standing in
  // for "pick a client", which is what CI hit on 2026-08-07.
  describe("with no client selected", () => {
    beforeEach(() => {
      mockActiveClient.mockResolvedValue(null);
    });

    it("says what to do next instead of reporting a failure", async () => {
      render(<DeliverablesTable />);
      expect(
        await screen.findByText("Pick a client first"),
      ).toBeInTheDocument();
      expect(screen.queryByRole("alert")).toBeNull();
    });

    it("never fires the tenant-scoped request at all", async () => {
      render(<DeliverablesTable />);
      await screen.findByText("Pick a client first");
      expect(mockFetch).not.toHaveBeenCalled();
    });

    it("keeps the page heading, so the surface stays identifiable", async () => {
      render(<DeliverablesTable />);
      await screen.findByText("Pick a client first");
      expect(
        screen.getByRole("heading", { name: "Deliverables", level: 1 }),
      ).toBeInTheDocument();
    });
  });
});
