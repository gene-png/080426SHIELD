import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * #1050: the shell capped every admin page at `max-w-6xl`, so a service
 * workspace's wide tables (Tech Debt step 2) scrolled sideways. Workspaces
 * under `/admin/services/<id>/...` run full-width; list and form pages keep
 * the readable cap.
 */

let pathname = "/admin/queue";
vi.mock("next/navigation", () => ({ usePathname: () => pathname }));
vi.mock("@/components/admin/AiStatusBanner", () => ({
  AiStatusBanner: () => null,
}));
vi.mock("@/components/site/SignOutButton", () => ({
  SignOutButton: () => null,
}));

import { AdminShell } from "./AdminShell";

function mainClasses(path: string): string[] {
  pathname = path;
  render(<AdminShell email="a@b.example">page</AdminShell>);
  return screen.getByRole("main").className.split(/\s+/);
}

describe("AdminShell main width", () => {
  beforeEach(() => {
    pathname = "/admin/queue";
  });

  it.each([
    "/admin/services/abc/tech-debt",
    "/admin/services/abc/csf",
    "/admin/services/abc/attack-coverage",
    "/admin/services/abc/zero-trust-cisa",
    "/admin/services/abc/zero-trust-dod",
  ])("runs the %s workspace full-width", (path) => {
    const classes = mainClasses(path);
    expect(classes).not.toContain("max-w-6xl");
    expect(classes).toContain("w-full");
  });

  it.each([
    "/admin/queue",
    "/admin/queue/abc",
    "/admin/deliverables",
    "/admin/management",
    "/admin/messages",
    "/admin/health",
    "/admin/audit",
    "/admin/risk-register",
    "/admin/services",
  ])("keeps the readable cap on %s", (path) => {
    expect(mainClasses(path)).toContain("max-w-6xl");
  });
});
