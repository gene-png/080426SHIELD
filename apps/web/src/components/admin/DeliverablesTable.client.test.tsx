import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as clientReads from "@/lib/admin/client-reads";
import * as deliverables from "@/lib/admin/deliverables";
import * as navigate from "@/lib/admin/navigate";

import { DeliverablesTable } from "./DeliverablesTable";

/**
 * RR-2 (for #1121): the Deliverables page's client comes from its own picker
 * and the URL (design note §3.1a, §3.3, §3.5). Through the real page: the
 * reads, the navigation and the deliverables fetch are mocked, and the real
 * resolver runs. List fixtures are shaped like `AdminClientListResponse`.
 */

const nav = vi.hoisted(() => ({ search: new URLSearchParams() }));
vi.mock("next/navigation", () => ({
  usePathname: () => "/admin/deliverables",
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
vi.mock("@/lib/admin/deliverables", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  fetchAdminDeliverables: vi.fn(),
}));

const STRING_5 =
  "Deliverables are listed per client. Choose a client above, then select Show this client.";
const STRING_7 =
  "The client saved in this browser is no longer listed. Choose a client above, then select Show this client.";
const STRING_11 =
  "SHIELD could not check which client is saved in this browser. Choose a client above, then select Show this client.";
const STRING_17A =
  "The client named in this page's link is not in the client list. Choose a client above, then select Show this client.";
const STRING_17B =
  "This page's link does not name a client. Choose a client above, then select Show this client.";
const SUBTITLE = /Every report produced for this organization/;

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
const UNLISTED = "cccccccc-0000-4000-8000-000000000003";

const readClientList = vi.mocked(clientReads.readClientList);
const readActiveClient = vi.mocked(clientReads.readActiveClient);
const fetchAdminDeliverables = vi.mocked(deliverables.fetchAdminDeliverables);
const leaveTo = vi.mocked(navigate.leaveTo);

function lists(clients: unknown[], active: unknown): void {
  readClientList.mockResolvedValue({ clients });
  readActiveClient.mockResolvedValue({ active });
}

function row(): deliverables.AdminDeliverableRow {
  return {
    id: "d1",
    service_id: "s1",
    service_kind: "nist_csf",
    service_title: "NIST CSF 2.0 Assessment",
    title: "Report",
    version: 1,
    status: "released",
    client_visible: true,
    finalized_at: "2026-02-01T00:00:00Z",
    released_at: "2026-02-02T00:00:00Z",
    pdf_artifact_id: "art-pdf",
    xlsx_artifact_id: null,
    docx_artifact_id: null,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  nav.search = new URLSearchParams();
  fetchAdminDeliverables.mockResolvedValue({ items: [row()] });
});

afterEach(() => {
  cleanup();
});

describe("Deliverables, scoped by its picker", () => {
  it("chosen: names the client, shows the subtitle, and fetches by its id", async () => {
    lists([A, B], B.id);
    render(<DeliverablesTable />);
    expect(
      await screen.findByRole("heading", {
        name: "Deliverables for Beacon LLC",
        level: 1,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText(SUBTITLE)).toBeInTheDocument();
    await screen.findByText("v1");
    expect(fetchAdminDeliverables).toHaveBeenCalledWith(
      B.id,
      expect.anything(),
    );
  });

  it("the download link carries the picker's client", async () => {
    nav.search = new URLSearchParams(`client=${B.id}`);
    lists([A, B], A.id);
    render(<DeliverablesTable />);
    expect(await screen.findByRole("link", { name: "PDF" })).toHaveAttribute(
      "href",
      `/api/proxy/artifacts/art-pdf/download?client_id=${B.id}`,
    );
  });

  it.each([
    ["unchosen", () => lists([A, B], null), STRING_5],
    ["stale", () => lists([A, B], UNLISTED), STRING_7],
    [
      "cookie_failed",
      () => {
        readClientList.mockResolvedValue({ clients: [A, B] });
        readActiveClient.mockRejectedValue(new Error("down"));
      },
      STRING_11,
    ],
    [
      "link_unlisted",
      () => {
        nav.search = new URLSearchParams(`client=${UNLISTED}`);
        lists([A], A.id);
      },
      STRING_17A,
    ],
    [
      "link_empty",
      () => {
        nav.search = new URLSearchParams("client=");
        lists([A], A.id);
      },
      STRING_17B,
    ],
  ])(
    "%s: its line, the bare h1, no subtitle, nothing fetched",
    async (_state, arrange, line) => {
      vi.spyOn(console, "error").mockImplementation(() => undefined);
      arrange();
      render(<DeliverablesTable />);
      expect(await screen.findByText(line)).toBeInTheDocument();
      expect(
        screen.getByRole("heading", { name: "Deliverables", level: 1 }),
      ).toBeInTheDocument();
      expect(screen.queryByText(SUBTITLE)).toBeNull();
      expect(fetchAdminDeliverables).not.toHaveBeenCalled();
    },
  );

  it("Apply from unchosen writes ?client=B; the new load names B and shows the subtitle", async () => {
    lists([A, B], null);
    render(<DeliverablesTable />);
    expect(await screen.findByText(STRING_5)).toBeInTheDocument();
    fireEvent.change(
      screen.getByRole("combobox", { name: "Client for this page" }),
      { target: { value: B.id } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Show this client" }));
    expect(leaveTo).toHaveBeenCalledWith(`/admin/deliverables?client=${B.id}`);

    cleanup();
    nav.search = new URLSearchParams(`client=${B.id}`);
    render(<DeliverablesTable />);
    await screen.findByRole("heading", {
      name: "Deliverables for Beacon LLC",
      level: 1,
    });
    expect(screen.getByText(SUBTITLE)).toBeInTheDocument();
    expect(screen.queryByText(STRING_5)).toBeNull();
  });

  it("a failed load keeps the header and shows the fetcher's sentence", async () => {
    lists([A], null);
    fetchAdminDeliverables.mockRejectedValue(
      new Error("Failed to load deliverables (504)."),
    );
    render(<DeliverablesTable />);
    expect(
      await screen.findByText("Failed to load deliverables (504)."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        name: "Deliverables for Atlas Corp",
        level: 1,
      }),
    ).toBeInTheDocument();
  });
});
