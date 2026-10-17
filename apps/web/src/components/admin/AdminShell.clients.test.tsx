import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

/**
 * T6: the shell's way into the client-scoped frame, and the frame's section
 * pages run full-width like the workspaces they wrap (#1050).
 */

const nav = vi.hoisted(() => ({ pathname: "/admin/queue" }));
vi.mock("next/navigation", () => ({
  usePathname: () => nav.pathname,
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/components/admin/AiStatusBanner", () => ({
  AiStatusBanner: () => null,
}));
vi.mock("@/components/site/SignOutButton", () => ({
  SignOutButton: () => null,
}));

import { AdminShell } from "./AdminShell";

function at(path: string): void {
  nav.pathname = path;
  render(<AdminShell email="a@b.example">page</AdminShell>);
}

describe("AdminShell and the client frame", () => {
  it("links to Clients from both primary navs", () => {
    at("/admin/queue");
    for (const el of screen.getAllByRole("navigation", { name: "Primary" }))
      expect(within(el).getByRole("link", { name: "Clients" })).toHaveAttribute(
        "href",
        "/admin/clients",
      );
  });

  it("marks Clients current anywhere under /admin/clients", () => {
    at("/admin/clients/c-1/services/csf/review");
    const [desktop] = screen.getAllByRole("navigation", { name: "Primary" });
    expect(
      within(desktop).getByRole("link", { name: "Clients" }),
    ).toHaveAttribute("aria-current", "page");
  });

  it.each([
    "/admin/clients/c-1/services/tech-debt/review",
    "/admin/clients/c-1/services/csf/overview",
  ])("runs the section page %s full-width", (path) => {
    at(path);
    expect(screen.getByRole("main").className.split(/\s+/)).not.toContain(
      "max-w-6xl",
    );
  });

  // #1385: a client's own pages run edge to edge; the frame owns their cap.
  // The clients list has no client, so it runs full-width like any such page.
  it.each(["/admin/clients"])("runs %s full-width", (path) => {
    at(path);
    expect(screen.getByRole("main").className.split(/\s+/)).not.toContain(
      "max-w-6xl",
    );
  });
});
