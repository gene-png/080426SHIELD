import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { IntakeOrgIndex } from "./IntakeOrgIndex";

import type { ClientSummary } from "@/lib/admin/client";

/**
 * The queue's job at 70 tenants is "let me find the one I want". Creation-order
 * cards made that scrolling-and-hoping, which is the complaint this surface was
 * changed to answer. The assertions below are about FINDABILITY, not layout.
 */

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/lib/admin/client", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  listClients: vi.fn(),
}));

const { listClients } = await import("@/lib/admin/client");
const mockList = vi.mocked(listClients);

function org(over: Partial<ClientSummary>): ClientSummary {
  return {
    id: "00000000-0000-4000-8000-000000000001",
    legal_name: "Acme",
    industry: null,
    intake_completed_at: null,
    open_request_count: 0,
    total_request_count: 0,
    ...over,
  } as ClientSummary;
}

beforeEach(() => {
  push.mockReset();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("IntakeOrgIndex", () => {
  it("lists every organization A-Z in the jump dropdown, whatever order the API returned", async () => {
    mockList.mockResolvedValue([
      org({ id: "id-zulu", legal_name: "Zulu Corp" }),
      org({ id: "id-alpha", legal_name: "alpha industries" }),
      org({ id: "id-mike", legal_name: "Mike Ltd" }),
    ]);
    render(<IntakeOrgIndex />);

    const select = await screen.findByRole("combobox", {
      name: "Jump to an organization",
    });
    const labels = Array.from(select.querySelectorAll("option")).map(
      (o) => o.textContent,
    );
    // Placeholder first, then case-insensitive alphabetical.
    expect(labels[0]).toContain("Select from 3 organizations");
    expect(labels.slice(1)).toEqual([
      "alpha industries",
      "Mike Ltd",
      "Zulu Corp",
    ]);
  });

  it("navigates to the organization the admin picks", async () => {
    mockList.mockResolvedValue([org({ id: "id-alpha", legal_name: "Alpha" })]);
    render(<IntakeOrgIndex />);

    const select = await screen.findByRole("combobox", {
      name: "Jump to an organization",
    });
    fireEvent.change(select, { target: { value: "id-alpha" } });
    await waitFor(() =>
      expect(push).toHaveBeenCalledWith("/admin/queue/id-alpha"),
    );
  });

  it("surfaces the awaiting-review count so the dropdown shows where the work is", async () => {
    mockList.mockResolvedValue([
      org({ id: "a", legal_name: "Busy Co", open_request_count: 3 }),
      org({ id: "b", legal_name: "Quiet Co", open_request_count: 0 }),
    ]);
    render(<IntakeOrgIndex />);

    const select = await screen.findByRole("combobox", {
      name: "Jump to an organization",
    });
    const labels = Array.from(select.querySelectorAll("option")).map(
      (o) => o.textContent,
    );
    expect(labels).toContain("Busy Co — 3 awaiting review");
    // No count on a quiet org: a "0 awaiting review" on every row is noise that
    // makes the ones that matter harder to spot.
    expect(labels).toContain("Quiet Co");
  });

  it("disambiguates tenants that share a legal name", async () => {
    // Three real tenants are called "Northwind Grid Cooperative". Identical rows
    // are exactly the confusion this page exists to remove.
    mockList.mockResolvedValue([
      org({
        id: "5b1e3d06-0000-4000-8000-000000000000",
        legal_name: "Northwind",
      }),
      org({
        id: "d903fa26-0000-4000-8000-000000000000",
        legal_name: "Northwind",
      }),
      org({
        id: "unique-0-0000-4000-8000-000000000000",
        legal_name: "Solo Ltd",
      }),
    ]);
    render(<IntakeOrgIndex />);

    await screen.findByRole("combobox", { name: "Jump to an organization" });
    expect(await screen.findByText(/\(id 5b1e3d06\)/)).toBeInTheDocument();
    expect(screen.getByText(/\(id d903fa26\)/)).toBeInTheDocument();
    // A unique name is left alone — the id is disambiguation, not decoration.
    expect(screen.queryByText(/\(id unique-0\)/)).toBeNull();
  });

  it("keeps the hint out of the control's accessible name", async () => {
    /**
     * Text inside a <label> becomes part of the control's accessible name, so
     * nesting the hint made a screen reader announce the whole sentence on every
     * focus. It belongs in aria-describedby.
     */
    mockList.mockResolvedValue([org({})]);
    render(<IntakeOrgIndex />);

    const select = await screen.findByRole("combobox", {
      name: "Jump to an organization",
    });
    expect(select).toHaveAccessibleName("Jump to an organization");
    expect(select).toHaveAccessibleDescription(/Every organization, A–Z/);
  });
});
