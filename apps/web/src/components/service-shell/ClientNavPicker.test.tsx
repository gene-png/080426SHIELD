/**
 * T6: the rail's client picker. It reuses the admin client list and the RR-2
 * picker, and NAVIGATES to the chosen client's frame. It never reads or writes
 * the active-client cookie: the frame's client is the URL's.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

import { ClientNavPicker } from "./ClientNavPicker";

let urls: string[];

function serve(status: number, body: unknown): void {
  urls = [];
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    urls.push(String(input));
    return new Response(JSON.stringify(body), { status });
  }) as unknown as typeof fetch;
}

const LIST = {
  clients: [
    { id: "c-1", legal_name: "Alpha Corp", dba_name: null },
    { id: "c-2", legal_name: "Beta LLC", dba_name: "Beta" },
  ],
};

beforeEach(() => {
  push.mockReset();
});

describe("ClientNavPicker", () => {
  it("navigates to the chosen client's frame and never touches the cookie", async () => {
    serve(200, LIST);
    render(<ClientNavPicker currentId="c-1" />);
    // Re-queried, not held: the picker remounts (a new `key`) once the list
    // arrives, so a select found while loading is a detached element.
    const picker = () =>
      screen.getByRole("combobox", { name: "Client for this page" });
    await waitFor(() => expect(picker()).toHaveValue("c-1"));
    fireEvent.change(picker(), { target: { value: "c-2" } });
    fireEvent.click(screen.getByRole("button", { name: "Show this client" }));
    expect(push).toHaveBeenCalledWith("/admin/clients/c-2");
    expect(urls).toEqual(["/api/proxy/admin/clients"]);
    expect(
      screen.getByRole("option", { name: "Beta (Beta LLC)" }),
    ).toBeInTheDocument();
  });

  it("starts at the placeholder when no client is chosen", async () => {
    serve(200, LIST);
    render(<ClientNavPicker currentId={null} />);
    await waitFor(() =>
      expect(screen.getByRole("option", { name: "Alpha Corp" })).toBeTruthy(),
    );
    expect(
      screen.getByRole("combobox", { name: "Client for this page" }),
    ).toHaveValue("");
  });

  it("says so when the list cannot be loaded", async () => {
    serve(500, {});
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    render(<ClientNavPicker currentId="c-1" />);
    expect(
      await screen.findByText(
        "The client list could not be loaded, so no client is selected.",
      ),
    ).toBeInTheDocument();
    expect(err).toHaveBeenCalled();
  });

  it("says so when there are no clients", async () => {
    serve(200, { clients: [] });
    render(<ClientNavPicker currentId={null} />);
    expect(await screen.findByText("No clients yet")).toBeInTheDocument();
  });
});
