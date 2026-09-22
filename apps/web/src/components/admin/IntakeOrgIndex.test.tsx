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

  // D-080 (#254): a self-serve tenant reaches this list with `legal_name` NULL.
  // Every one of the three reads below — sort key, dedupe key, option label —
  // called a string method on that column, so an unnamed org did not render a
  // blank row, it threw and took the whole page with it.
  it("renders an organization nobody has named yet, instead of crashing the page", async () => {
    mockList.mockResolvedValue([
      org({ id: "id-named", legal_name: "Zulu Corp" }),
      org({ id: "id-unnamed", legal_name: null }),
    ]);
    render(<IntakeOrgIndex />);

    const select = await screen.findByRole("combobox", {
      name: "Jump to an organization",
    });
    const labels = Array.from(select.querySelectorAll("option")).map(
      (o) => o.textContent,
    );
    // Both rows present: the named one is proof the list rendered at all, so a
    // page that failed to load cannot satisfy this assertion vacuously.
    expect(labels).toContain("Zulu Corp");
    expect(labels).toContain("(pending intake)");
    expect(labels[0]).toContain("Select from 2 organizations");
  });

  it("disambiguates SEVERAL unnamed organizations in the jump list", async () => {
    /**
     * The regression the one-unnamed-org tests structurally could not express.
     *
     * Since D-080 every unnamed org renders the identical label, so N of them
     * became N byte-identical <option>s -- and the page the admin lands on
     * identifies the tenant nowhere either, so there is no second chance to
     * tell them apart. Before D-080 each self-serve tenant carried a distinct
     * domain- or person-derived name, which is why this was not needed then.
     *
     * Two unnamed orgs is the minimum that can fail; one can never fail.
     *
     * The ids differ in their FIRST EIGHT characters, deliberately. The
     * disambiguator on this surface is `id.slice(0, 8)` -- pre-existing, and
     * what the card rows have always used -- so two ids sharing that prefix
     * are not distinguished by it. The first draft of this fixture used
     * `...aa` and `...bb`, which differ only in their LAST two characters, and
     * it failed against a correct implementation: a state real UUIDs do not
     * produce (a shared 8-hex-char prefix is ~1 in 4 billion), so the test was
     * about a different system than the one that ships.
     *
     * Residual, stated rather than left implicit: ids that DO share an 8-char
     * prefix still collide here. Pre-existing, unchanged by D-080, and not
     * worth widening the label for.
     */
    mockList.mockResolvedValue([
      org({ id: "5b1e3d06-0000-4000-8000-0000000000aa", legal_name: null }),
      org({ id: "d903fa26-0000-4000-8000-0000000000bb", legal_name: null }),
    ]);
    render(<IntakeOrgIndex />);

    const select = await screen.findByRole("combobox");
    const options = Array.from(select.querySelectorAll("option")).filter(
      (o) => (o as HTMLOptionElement).value !== "",
    );
    expect(options).toHaveLength(2);

    const labels = options.map((o) => o.textContent ?? "");
    expect(new Set(labels).size).toBe(2);
    expect(labels[0]).toContain("5b1e3d06");
    expect(labels[1]).toContain("d903fa26");
  });

  it("keeps an unnamed organization reachable from the jump list", async () => {
    // Findability is the whole job of this surface, and an admin triaging a
    // fresh signup has nothing but the label to click.
    mockList.mockResolvedValue([org({ id: "id-unnamed", legal_name: null })]);
    render(<IntakeOrgIndex />);

    const select = await screen.findByRole("combobox", {
      name: "Jump to an organization",
    });
    fireEvent.change(select, { target: { value: "id-unnamed" } });
    await waitFor(() =>
      expect(push).toHaveBeenCalledWith("/admin/queue/id-unnamed"),
    );
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
    // TWO surfaces carry the hint since the jump <select> gained it: the
    // <option> and the card row. This test asserted a single match and began
    // failing when the option-side hint shipped.
    //
    // Updated to assert BOTH, which is the current intent -- deliberately not
    // relaxed to `getAllByText(...)[0]`, which would go green while the
    // option-side hint, the surface the change was made FOR, silently
    // disappeared again.
    expect(await screen.findAllByText(/\(id 5b1e3d06\)/)).toHaveLength(2);
    expect(screen.getAllByText(/\(id d903fa26\)/)).toHaveLength(2);
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
