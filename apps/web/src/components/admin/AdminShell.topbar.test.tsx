import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * #1385: the admin links move from the left column to one bar under the page
 * header, at every width. Risk Register leaves the bar (each client's own list
 * links to its register; the URL keeps working). The left column is for the
 * CLIENT: a page under a client's frame runs edge to edge so the frame's rail
 * is that column; a page with no client has no column.
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

function at(path: string, search = ""): void {
  nav.pathname = path;
  nav.search = search;
  render(<AdminShell email="a@b.example">page</AdminShell>);
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
    at("/admin/messages", "client=abc");
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

describe("a client's page runs edge to edge, the frame owns its padding (#1385)", () => {
  it.each([
    "/admin/clients/c-1",
    "/admin/clients/c-1/services/csf/overview",
    "/admin/clients/c-1/services/tech-debt",
  ])("%s: main has no padding and no cap", (path) => {
    at(path);
    const classes = screen.getByRole("main").className.split(/\s+/);
    expect(classes).not.toContain("max-w-6xl");
    expect(classes).not.toContain("px-6");
    expect(classes).toContain("w-full");
  });

  it.each(["/admin/clients", "/admin/queue", "/admin/audit"])(
    "%s: no client, so main keeps its padding and runs full-width",
    (path) => {
      at(path);
      const classes = screen.getByRole("main").className.split(/\s+/);
      expect(classes).not.toContain("max-w-6xl");
      expect(classes).toContain("px-6");
    },
  );
});
