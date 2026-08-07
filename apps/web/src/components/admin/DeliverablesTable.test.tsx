import "@testing-library/jest-dom/vitest";

import { render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

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

const { fetchAdminDeliverables } = await import("@/lib/admin/deliverables");
const mockFetch = vi.mocked(fetchAdminDeliverables);

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
});
