import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

/**
 * #1385: the client's rail is the left column of a client's page, before the
 * page in reading order, and the page keeps the padding and cap the shell
 * stopped applying around it.
 */
const nav = vi.hoisted(() => ({ pathname: "/admin/clients/c-1" }));
vi.mock("next/navigation", () => ({ usePathname: () => nav.pathname }));

import { ClientFrameBody } from "./ClientFrameBody";

function at(path: string): void {
  nav.pathname = path;
  render(
    <ClientFrameBody rail={<div data-testid="the-rail">rail</div>}>
      <p>the page</p>
    </ClientFrameBody>,
  );
}

describe("ClientFrameBody (#1385)", () => {
  it("puts the rail in the left column, before the page", () => {
    at("/admin/clients/c-1");
    const column = screen.getByTestId("client-left-column");
    expect(within(column).getByTestId("the-rail")).toBeVisible();
    const page = screen.getByTestId("client-frame-page");
    expect(within(page).getByText("the page")).toBeVisible();
    expect(
      column.compareDocumentPosition(page) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("keeps the readable cap on a client's overview", () => {
    at("/admin/clients/c-1");
    expect(
      screen.getByTestId("client-frame-page").className.split(/\s+/),
    ).toContain("max-w-6xl");
  });

  it("runs a section page full-width, like the workspace it wraps", () => {
    at("/admin/clients/c-1/services/tech-debt/review");
    expect(
      screen.getByTestId("client-frame-page").className.split(/\s+/),
    ).not.toContain("max-w-6xl");
  });

  it("stacks the rail above the page on narrow screens, beside it from md up", () => {
    at("/admin/clients/c-1");
    const body = screen.getByTestId("client-left-column").parentElement;
    const classes = (body?.className ?? "").split(/\s+/);
    expect(classes).toContain("flex-col");
    expect(classes).toContain("md:flex-row");
  });
});
