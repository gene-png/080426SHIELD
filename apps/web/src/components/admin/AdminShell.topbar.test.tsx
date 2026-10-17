import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * #1385: the admin links move from the left column to one bar under the page
 * header, at every width. Risk Register leaves the bar (each client's own list
 * links to its register; the URL keeps working). The left column is for the
 * CLIENT: a page with a client shows the rail the route hands the shell, and a
 * page with none shows no column at all.
 */

const nav = vi.hoisted(() => ({ pathname: "/admin/queue", search: "" }));
vi.mock("next/navigation", () => ({
  usePathname: () => nav.pathname,
  useSearchParams: () => new URLSearchParams(nav.search),
}));
vi.mock("@/components/admin/AiStatusBanner", () => ({
  AiStatusBanner: () => null,
}));
vi.mock("@/components/site/SignOutButton", () => ({
  SignOutButton: () => null,
}));

import { AdminShell } from "./AdminShell";

const LINKS = [
  ["Intake Queue", "/admin/queue"],
  ["Clients", "/admin/clients"],
  ["Deliverables", "/admin/deliverables"],
  ["Messages", "/admin/messages"],
  ["Audit", "/admin/audit"],
  ["System Health", "/admin/health"],
  ["Management", "/admin/management"],
] as const;

function at(path: string, rail?: React.ReactNode, search = ""): void {
  nav.pathname = path;
  nav.search = search;
  render(
    <AdminShell email="a@b.example" rail={rail}>
      page
    </AdminShell>,
  );
}

beforeEach(() => {
  nav.pathname = "/admin/queue";
  nav.search = "";
});

describe("the admin top bar (#1385)", () => {
  it("is ONE primary navigation, not a sidebar plus a mobile row", () => {
    at("/admin/queue");
    expect(screen.getAllByRole("navigation", { name: "Primary" })).toHaveLength(
      1,
    );
    expect(screen.queryByLabelText("Admin navigation")).toBeNull();
  });

  it("holds exactly the seven links, in order, and no Risk Register", () => {
    at("/admin/queue");
    const bar = screen.getByRole("navigation", { name: "Primary" });
    const links = within(bar).getAllByRole("link");
    expect(links.map((l) => [l.textContent, l.getAttribute("href")])).toEqual(
      LINKS.map(([label, href]) => [label, href]),
    );
    expect(
      within(bar).queryByRole("link", { name: "Risk Register" }),
    ).toBeNull();
  });

  it("sits in the header's row, wraps instead of scrolling sideways", () => {
    at("/admin/queue");
    const classes = screen
      .getByRole("navigation", { name: "Primary" })
      .className.split(/\s+/);
    expect(classes).toContain("flex-wrap");
    expect(classes.join(" ")).not.toMatch(/overflow-x/);
  });

  it.each(LINKS)("marks %s current on %s and no other link", (label, href) => {
    at(href);
    const bar = screen.getByRole("navigation", { name: "Primary" });
    const current = within(bar)
      .getAllByRole("link")
      .filter((l) => l.getAttribute("aria-current") === "page")
      .map((l) => l.textContent);
    expect(current).toEqual([label]);
  });

  it("carries ?client to the twin pages from a twin page, as before", () => {
    at("/admin/messages", undefined, "client=abc");
    const bar = screen.getByRole("navigation", { name: "Primary" });
    expect(
      within(bar).getByRole("link", { name: "Deliverables" }),
    ).toHaveAttribute("href", "/admin/deliverables?client=abc");
    expect(within(bar).getByRole("link", { name: "Audit" })).toHaveAttribute(
      "href",
      "/admin/audit",
    );
  });

  it("keeps the SHIELD brand link to the queue in the header", () => {
    at("/admin/queue");
    expect(screen.getByRole("link", { name: /SHIELD/ })).toHaveAttribute(
      "href",
      "/admin/queue",
    );
  });
});

describe("the left column is the client (#1385)", () => {
  it("shows the rail the route passes, before the page's main", () => {
    at(
      "/admin/clients/c-1/services/csf/overview",
      <div data-testid="the-rail">rail</div>,
    );
    const column = screen.getByTestId("admin-left-column");
    expect(within(column).getByTestId("the-rail")).toBeVisible();
    const main = screen.getByRole("main");
    expect(
      column.compareDocumentPosition(main) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("shows no column on a page with no client", () => {
    at("/admin/queue");
    expect(screen.queryByTestId("admin-left-column")).toBeNull();
  });
});
