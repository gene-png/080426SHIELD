import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as clientReads from "@/lib/admin/client-reads";
import * as navigate from "@/lib/admin/navigate";
import * as messages from "@/lib/messages/client";

import { InboxView } from "./InboxView";

/**
 * RR-2 (for #1121): the admin Messages page's client comes from its own
 * picker and the URL, and its h1 and subtitle depend on it (design note §3.5).
 * Through the real component; the reads, the navigation and the inbox fetch
 * are mocked. List fixtures are shaped like `AdminClientListResponse`.
 */

const nav = vi.hoisted(() => ({ search: new URLSearchParams() }));
vi.mock("next/navigation", () => ({
  usePathname: () => "/admin/messages",
  useSearchParams: () => nav.search,
}));
vi.mock("@/lib/admin/client-reads", () => ({
  readClientList: vi.fn(),
  readActiveClient: vi.fn(),
}));
vi.mock("@/lib/admin/navigate", () => ({
  leaveTo: vi.fn(),
  reloadPage: vi.fn(),
}));
vi.mock("@/lib/messages/client", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  fetchInbox: vi.fn(),
}));

const STRING_6 =
  "Messages are listed per client. Choose a client above, then select Show this client.";
const STRING_9 =
  "Threads appear here once a service for this client has a conversation.";
const STRING_13 =
  "Threads for the client chosen above, newest first. The badge counts messages you haven't opened yet.";
const STRING_7 =
  "The client saved in this browser is no longer listed. Choose a client above, then select Show this client.";

function summary(id: string, legal_name: string) {
  return {
    id,
    legal_name,
    dba_name: null,
    industry: null,
    size_band: null,
    intake_completed_at: null,
    created_at: "2026-10-01T00:00:00Z",
    archived_at: null,
    open_request_count: 0,
    total_request_count: 0,
  };
}
const A = summary("aaaaaaaa-0000-4000-8000-000000000001", "Atlas Corp");
const B = summary("bbbbbbbb-0000-4000-8000-000000000002", "Beacon LLC");

const readClientList = vi.mocked(clientReads.readClientList);
const readActiveClient = vi.mocked(clientReads.readActiveClient);
const fetchInbox = vi.mocked(messages.fetchInbox);
const leaveTo = vi.mocked(navigate.leaveTo);

function lists(clients: unknown[], active: unknown): void {
  readClientList.mockResolvedValue({ clients });
  readActiveClient.mockResolvedValue({ active });
}

beforeEach(() => {
  vi.clearAllMocks();
  nav.search = new URLSearchParams();
  fetchInbox.mockResolvedValue({ threads: [], unread_total: 0 });
});

afterEach(() => {
  cleanup();
});

describe("Messages, scoped by its picker", () => {
  it("chosen: string 3 as the h1, string 13 as the subtitle, the inbox read by id", async () => {
    nav.search = new URLSearchParams(`client=${B.id}`);
    lists([A, B], A.id);
    render(<InboxView />);
    expect(
      await screen.findByRole("heading", { name: "Messages for Beacon LLC" }),
    ).toBeInTheDocument();
    expect(screen.getByText(STRING_13)).toBeInTheDocument();
    expect(await screen.findByText(STRING_9)).toBeInTheDocument();
    expect(fetchInbox).toHaveBeenCalledWith(B.id);
    expect(fetchInbox).not.toHaveBeenCalledWith(A.id);
  });

  it("unchosen: 'Pick a client first' with string 6, the bare h1, no subtitle, nothing fetched", async () => {
    lists([A, B], null);
    render(<InboxView />);
    expect(await screen.findByText(STRING_6)).toBeInTheDocument();
    expect(screen.getByText("Pick a client first")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Messages" }),
    ).toBeInTheDocument();
    expect(screen.queryByText(STRING_13)).toBeNull();
    expect(fetchInbox).not.toHaveBeenCalled();
  });

  it("stale: string 7 and no subtitle", async () => {
    lists([A, B], "cccccccc-0000-4000-8000-000000000003");
    render(<InboxView />);
    expect(await screen.findByText(STRING_7)).toBeInTheDocument();
    expect(screen.queryByText(STRING_13)).toBeNull();
    expect(fetchInbox).not.toHaveBeenCalled();
  });

  it("Apply from unchosen writes ?client=B; the new load shows string 3 and 13", async () => {
    lists([A, B], null);
    render(<InboxView />);
    expect(await screen.findByText(STRING_6)).toBeInTheDocument();
    fireEvent.change(
      screen.getByRole("combobox", { name: "Client for this page" }),
      { target: { value: B.id } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Show this client" }));
    expect(leaveTo).toHaveBeenCalledWith(`/admin/messages?client=${B.id}`);

    cleanup();
    nav.search = new URLSearchParams(`client=${B.id}`);
    render(<InboxView />);
    await screen.findByRole("heading", { name: "Messages for Beacon LLC" });
    expect(screen.getByText(STRING_13)).toBeInTheDocument();
    expect(screen.queryByText(STRING_6)).toBeNull();
  });
});
