import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

/**
 * RR-2 (for #1121), design note §3.6: on the three pages that share a client
 * picker, the sidebar's links to those pages carry the URL's `client`, so a
 * move between them keeps the choice. Nothing else carries it.
 */

const nav = vi.hoisted(() => ({
  pathname: "/admin/queue",
  search: new URLSearchParams(),
}));
vi.mock("next/navigation", () => ({
  usePathname: () => nav.pathname,
  useSearchParams: () => nav.search,
}));
vi.mock("@/components/admin/AiStatusBanner", () => ({
  AiStatusBanner: () => null,
}));
vi.mock("@/components/site/SignOutButton", () => ({
  SignOutButton: () => null,
}));

import { AdminShell } from "./AdminShell";

const TWINS = ["Deliverables", "Risk Register", "Messages"];
const OTHERS = ["Intake Queue", "Audit", "System Health", "Management"];
const BASE: Record<string, string> = {
  "Intake Queue": "/admin/queue",
  Deliverables: "/admin/deliverables",
  "Risk Register": "/admin/risk-register",
  Messages: "/admin/messages",
  Audit: "/admin/audit",
  "System Health": "/admin/health",
  Management: "/admin/management",
};

/** Every primary nav: the desktop sidebar and the mobile row. */
function hrefsIn(label: string): string[] {
  return screen
    .getAllByRole("navigation", { name: "Primary" })
    .map(
      (navEl) =>
        within(navEl).getByRole("link", { name: label }).getAttribute("href") ??
        "",
    );
}

function at(pathname: string, search: string): void {
  nav.pathname = pathname;
  nav.search = new URLSearchParams(search);
  render(<AdminShell email="a@b.example">page</AdminShell>);
}

afterEach(() => {
  cleanup();
});

describe("AdminShell twin links (§3.6)", () => {
  it("on Deliverables with ?client=B, the twin links carry it and the others do not", () => {
    at("/admin/deliverables", "client=b-1");
    expect(screen.getAllByRole("navigation", { name: "Primary" })).toHaveLength(
      2,
    );
    for (const label of TWINS)
      expect(hrefsIn(label)).toEqual(
        Array(2).fill(`${BASE[label]}?client=b-1`),
      );
    for (const label of OTHERS)
      expect(hrefsIn(label)).toEqual(Array(2).fill(BASE[label]));
  });

  it("on the Intake Queue with ?client=B, no link carries it", () => {
    at("/admin/queue", "client=b-1");
    for (const label of [...TWINS, ...OTHERS])
      expect(hrefsIn(label)).toEqual(Array(2).fill(BASE[label]));
  });

  it("on Messages with no parameter, no link carries one", () => {
    at("/admin/messages", "");
    for (const label of [...TWINS, ...OTHERS])
      expect(hrefsIn(label)).toEqual(Array(2).fill(BASE[label]));
  });

  it("encodes an id that needs it", () => {
    at("/admin/risk-register", "client=odd%20id%2F1");
    expect(hrefsIn("Messages")).toEqual(
      Array(2).fill("/admin/messages?client=odd%20id%2F1"),
    );
  });

  it("keeps aria-current on the path alone", () => {
    at("/admin/deliverables", "client=b-1");
    const [desktop] = screen.getAllByRole("navigation", { name: "Primary" });
    expect(
      within(desktop).getByRole("link", { name: "Deliverables" }),
    ).toHaveAttribute("aria-current", "page");
  });
});
