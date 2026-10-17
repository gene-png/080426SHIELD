import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * #1385: the client's rail moved from the client layout to the `@rail` slot of
 * the admin layout, so the admin shell can put it in its left column. The slot
 * is the rail's only producer now: it must check the client like the layout
 * does, and every URL that is NOT a client's page must match the slot with
 * nothing (a slot with no match keeps its last content on a soft navigation).
 */

const frame = vi.hoisted(() => ({
  load: vi.fn(),
}));
vi.mock("@/lib/admin/client-route", () => ({
  loadClientFrame: frame.load,
}));
vi.mock("@/components/service-shell/ClientRail", () => ({
  ClientRail: (p: { client: { id: string; label: string } }) => (
    <div data-testid="the-rail" data-client={p.client.id}>
      {p.client.label}
    </div>
  ),
}));

import RailDefault from "./default";
import NoRail from "./[[...rest]]/page";
import ClientRailSlot from "./clients/[clientId]/[[...rest]]/page";

beforeEach(() => {
  frame.load.mockReset();
});

describe("the @rail slot for a client", () => {
  it("renders the rail of the client in the URL, with that client's services", async () => {
    frame.load.mockResolvedValue({
      client: { id: "c-1", label: "Atlas" },
      services: [],
    });
    render(await ClientRailSlot({ params: Promise.resolve({ clientId: "c-1" }) }));
    expect(frame.load).toHaveBeenCalledWith("c-1");
    expect(screen.getByTestId("the-rail")).toHaveAttribute("data-client", "c-1");
    expect(screen.getByText("Atlas")).toBeVisible();
  });

  it("refuses like the layout does: the check's refusal is not swallowed", async () => {
    frame.load.mockRejectedValue(new Error("not found"));
    await expect(
      ClientRailSlot({ params: Promise.resolve({ clientId: "nope" }) }),
    ).rejects.toThrow("not found");
  });
});

describe("the @rail slot for every other URL", () => {
  it("renders nothing, so a soft navigation clears the previous rail", () => {
    expect(NoRail()).toBeNull();
    expect(RailDefault()).toBeNull();
  });
});
