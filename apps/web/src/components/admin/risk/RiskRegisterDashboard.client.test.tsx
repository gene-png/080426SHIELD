import "@testing-library/jest-dom/vitest";

import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as clientReads from "@/lib/admin/client-reads";
import * as navigate from "@/lib/admin/navigate";
import * as riskClient from "@/lib/risk/client";
import type { RiskEntry, RiskGate, RiskRegister } from "@/lib/risk/types";

import { RiskRegisterDashboard } from "./RiskRegisterDashboard";

/**
 * RR-2 (for #1121): the Risk Register's client comes from its own picker, the
 * URL's `?client=` and the mount-time reads (design note §3.1a, §3.3), never
 * from the shared cookie alone. Through the real page: only the reads, the
 * navigation and the risk api are mocked, and the real resolver runs.
 *
 * The list fixtures are shaped like the API's `AdminClientListResponse`
 * (`apps/api/app/schemas/admin.py`), every `AdminClientSummary` field included.
 * The copy is §7's, approved verbatim, spelled out here rather than imported.
 */

const nav = vi.hoisted(() => ({
  search: new URLSearchParams(),
  pathname: "/admin/risk-register",
}));
vi.mock("next/navigation", () => ({
  usePathname: () => nav.pathname,
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
vi.mock("@/lib/risk/client", () => ({
  describeRiskError: (e: unknown) => String(e),
  editRiskEntryRating: vi.fn(),
  exportRiskRegister: vi.fn(),
  fetchRiskGate: vi.fn(),
  fetchRiskRegisterLatest: vi.fn(),
  generateRiskRegister: vi.fn(),
  publishRiskRegister: vi.fn(),
}));
vi.mock("@/components/admin/RunAiGuard", () => ({
  RunAiGuard: ({
    children,
    onProceed,
  }: {
    children: (p: {
      onClick: () => void;
      statusUnknown: boolean;
    }) => React.ReactNode;
    onProceed: () => void;
  }) => children({ onClick: onProceed, statusUnknown: false }),
}));

const STRING_4 =
  "The Risk Register is generated per client. Choose a client above, then select Show this client.";
const STRING_7 =
  "The client saved in this browser is no longer listed. Choose a client above, then select Show this client.";
const STRING_8 =
  "The client list could not be loaded, so no client is selected.";
const STRING_11 =
  "SHIELD could not check which client is saved in this browser. Choose a client above, then select Show this client.";
const STRING_17A =
  "The client named in this page's link is not in the client list. Choose a client above, then select Show this client.";
const STRING_17B =
  "This page's link does not name a client. Choose a client above, then select Show this client.";
const string18 = (label: string) =>
  `Opening ${label}. If this page does not change, reload it, then choose the client again.`;
const STARTING_LINES = [STRING_4, STRING_7, STRING_11, STRING_17A, STRING_17B];

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
const leaveTo = vi.mocked(navigate.leaveTo);
const reloadPage = vi.mocked(navigate.reloadPage);
const fetchRiskGate = vi.mocked(riskClient.fetchRiskGate);
const fetchRiskRegisterLatest = vi.mocked(riskClient.fetchRiskRegisterLatest);
const generateRiskRegister = vi.mocked(riskClient.generateRiskRegister);
const exportRiskRegister = vi.mocked(riskClient.exportRiskRegister);
const publishRiskRegister = vi.mocked(riskClient.publishRiskRegister);
const editRiskEntryRating = vi.mocked(riskClient.editRiskEntryRating);
const fetchSpy = vi.fn();

function gate(over: Partial<RiskGate> = {}): RiskGate {
  return {
    unlocked: true,
    has_attack: true,
    has_csf: true,
    has_zt: true,
    missing: [],
    not_finalized: [],
    synthesizable_missing: [],
    attack_catalog_mismatch: null,
    inputs: [],
    ...over,
  };
}

function entry(over: Partial<RiskEntry> = {}): RiskEntry {
  return {
    id: "e1",
    title: "Credential theft",
    description: null,
    axis: "detection",
    source: "coverage_finding",
    source_id: "T1078",
    linked_techniques: [],
    linked_controls: [],
    likelihood: "low",
    impact: "minor",
    tier: "negligible",
    compensating_controls: null,
    residual_risk: null,
    recommended_action: "remediate",
    rationale: null,
    origin: "ai_generated",
    trust: "admin_assisted",
    dropped_links: {},
    source_state: null,
    source_review_pending: false,
    rating_edited_by: null,
    rating_edited_at: null,
    ...over,
  };
}

function register(over: Partial<RiskRegister> = {}): RiskRegister {
  return {
    batches_total: null,
    batches_failed: null,
    entries_intended: null,
    excluded_inputs: [],
    excluded_inputs_recorded: true,
    entries_total: 1,
    entries_without_tier: 0,
    entries_with_dropped_links: 0,
    entries_unlinked_after_drops: 0,
    entries_links_not_recorded: 0,
    excluded_unscored_links: [],
    excluded_unscored_links_recorded: false,
    dropped_citations: null,
    findings_recorded: false,
    findings_total: null,
    findings_without_entry: [],
    findings_with_several_entries: {},
    ratings_carried_recorded: false,
    ratings_carried: null,
    ratings_carried_from_version: null,
    ratings_not_carried: [],
    id: "r1",
    client_id: A.id,
    version: 1,
    generated_by: null,
    finalized_at: null,
    created_at: "2026-10-04T00:00:00Z",
    xlsx_artifact_id: "art-x",
    pdf_artifact_id: null,
    docx_artifact_id: null,
    xlsx_filename: "register.xlsx",
    pdf_filename: null,
    docx_filename: null,
    entries: [entry()],
    tier_counts: {},
    axis_counts: {},
    action_counts: {},
    ...over,
  };
}

function setUrl(search: string): void {
  nav.search = new URLSearchParams(search);
}

function lists(clients: unknown[], active: unknown): void {
  readClientList.mockResolvedValue({ clients });
  readActiveClient.mockResolvedValue({ active });
}

function picker(): HTMLSelectElement {
  return screen.getByRole("combobox", { name: "Client for this page" });
}

function applyButton(): HTMLElement {
  return screen.getByRole("button", { name: "Show this client" });
}

function choose(id: string): void {
  fireEvent.change(picker(), { target: { value: id } });
}

async function headingFor(label: string): Promise<void> {
  await screen.findByRole("heading", { name: `Risk Register for ${label}` });
}

/** The body has loaded: its status line replaces "Loading…". */
async function loadedFor(label: string): Promise<void> {
  await headingFor(label);
  await screen.findByText(/· version \d+|· not yet generated/);
}

function noPostToActiveClient(): void {
  expect(
    fetchSpy.mock.calls.filter(
      ([url, init]) =>
        String(url).includes("/api/active-client") &&
        (init as RequestInit | undefined)?.method === "POST",
    ),
  ).toEqual([]);
}

beforeEach(() => {
  vi.clearAllMocks();
  setUrl("");
  nav.pathname = "/admin/risk-register";
  fetchSpy.mockReset();
  vi.stubGlobal("fetch", fetchSpy);
  fetchRiskGate.mockResolvedValue(gate());
  fetchRiskRegisterLatest.mockResolvedValue(register());
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("each reader result on the Risk Register (§3.1, §3.1a)", () => {
  it("list_failed: string 8, no picker, nothing tenant-scoped fetched", async () => {
    readClientList.mockRejectedValue(new Error("down"));
    readActiveClient.mockRejectedValue(new Error("down"));
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(<RiskRegisterDashboard />);
    expect(await screen.findByRole("alert")).toHaveTextContent(STRING_8);
    expect(
      screen.getByRole("heading", { name: "Risk Register" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Show this client" }),
    ).toBeNull();
    expect(fetchRiskGate).not.toHaveBeenCalled();
    noPostToActiveClient();
  });

  it("a 200 list without `clients` is list_failed, never 'No clients yet'", async () => {
    readClientList.mockResolvedValue({});
    readActiveClient.mockResolvedValue({ active: null });
    render(<RiskRegisterDashboard />);
    expect(await screen.findByRole("alert")).toHaveTextContent(STRING_8);
    expect(screen.queryByText("No clients yet")).toBeNull();
  });

  it("cookie_failed: string 11, and the list is still offered", async () => {
    readClientList.mockResolvedValue({ clients: [A, B] });
    readActiveClient.mockRejectedValue(new Error("down"));
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(<RiskRegisterDashboard />);
    expect(await screen.findByRole("alert")).toHaveTextContent(STRING_11);
    expect(
      within(picker()).getByRole("option", { name: "Beacon LLC" }),
    ).toBeInTheDocument();
    expect(fetchRiskGate).not.toHaveBeenCalled();
    noPostToActiveClient();
  });

  it("none: 'No clients yet', nothing fetched", async () => {
    lists([], null);
    render(<RiskRegisterDashboard />);
    expect(await screen.findByText("No clients yet")).toBeInTheDocument();
    expect(fetchRiskGate).not.toHaveBeenCalled();
  });

  it("chosen by the cookie: the header names it and its register is read", async () => {
    lists([A, B], B.id);
    render(<RiskRegisterDashboard />);
    await loadedFor("Beacon LLC");
    expect(fetchRiskGate).toHaveBeenCalledWith(B.id);
    expect(fetchRiskRegisterLatest).toHaveBeenCalledWith(B.id);
    expect(fetchRiskGate).not.toHaveBeenCalledWith(A.id);
    noPostToActiveClient();
  });

  it("chosen as the one client, with no cookie", async () => {
    lists([A], null);
    render(<RiskRegisterDashboard />);
    await loadedFor("Atlas Corp");
    expect(fetchRiskGate).toHaveBeenCalledWith(A.id);
  });

  it("stale: string 7, nothing tenant-scoped fetched", async () => {
    lists([A, B], UNLISTED);
    render(<RiskRegisterDashboard />);
    expect(await screen.findByRole("status")).toHaveTextContent(STRING_7);
    expect(fetchRiskGate).not.toHaveBeenCalled();
  });

  it("unchosen: 'Pick a client first' with string 4, and no Management link", async () => {
    lists([A, B], null);
    render(<RiskRegisterDashboard />);
    expect(await screen.findByText(STRING_4)).toBeInTheDocument();
    expect(screen.getByText("Pick a client first")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Go to Management" })).toBeNull();
    expect(fetchRiskGate).not.toHaveBeenCalled();
    noPostToActiveClient();
  });

  it("loading: while the list is pending, the bare h1 and a disabled picker, nothing fetched", async () => {
    readClientList.mockReturnValue(new Promise(() => undefined));
    readActiveClient.mockResolvedValue({ active: A.id });
    render(<RiskRegisterDashboard />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Risk Register" }),
    ).toBeInTheDocument();
    expect(picker()).toBeDisabled();
    await act(async () => undefined);
    expect(fetchRiskGate).not.toHaveBeenCalled();
  });

  it("loading: with the list in and the cookie pending, the options are there but disabled", async () => {
    readClientList.mockResolvedValue({ clients: [A, B] });
    readActiveClient.mockReturnValue(new Promise(() => undefined));
    render(<RiskRegisterDashboard />);
    await waitFor(() =>
      expect(
        within(picker()).getByRole("option", { name: "Atlas Corp" }),
      ).toBeInTheDocument(),
    );
    expect(picker()).toBeDisabled();
    expect(screen.getByText("Loading…")).toBeInTheDocument();
    expect(fetchRiskGate).not.toHaveBeenCalled();
  });
});

describe("the URL's ?client= (§3.1a rows 3 and 4)", () => {
  it("names B while the cookie names A: B's register, nothing for A, no string 7", async () => {
    setUrl(`client=${B.id}`);
    lists([A, B], A.id);
    render(<RiskRegisterDashboard />);
    await loadedFor("Beacon LLC");
    expect(fetchRiskGate).toHaveBeenCalledWith(B.id);
    expect(fetchRiskGate).not.toHaveBeenCalledWith(A.id);
    expect(screen.queryByText(STRING_7)).toBeNull();
  });

  it("an unlisted id: string 17a, nothing fetched, even with exactly one client", async () => {
    setUrl(`client=${UNLISTED}`);
    lists([A], A.id);
    render(<RiskRegisterDashboard />);
    expect(await screen.findByRole("status")).toHaveTextContent(STRING_17A);
    expect(fetchRiskGate).not.toHaveBeenCalled();
  });

  it.each(["client=", "client"])(
    "?%s: string 17b, nothing fetched, even with exactly one client",
    async (search) => {
      setUrl(search);
      lists([A], A.id);
      render(<RiskRegisterDashboard />);
      expect(await screen.findByRole("status")).toHaveTextContent(STRING_17B);
      expect(fetchRiskGate).not.toHaveBeenCalled();
    },
  );
});

describe("Apply (§3.3)", () => {
  it("is disabled on the placeholder and on the current client", async () => {
    lists([A, B], A.id);
    render(<RiskRegisterDashboard />);
    await loadedFor("Atlas Corp");
    expect(picker().value).toBe(A.id);
    expect(applyButton()).toBeDisabled();
    choose("");
    expect(applyButton()).toBeDisabled();
    choose(B.id);
    expect(applyButton()).toBeEnabled();
  });

  it("A→B is a full page load of ?client=B, with no cookie POST; the new load reads B", async () => {
    lists([A, B], A.id);
    render(<RiskRegisterDashboard />);
    await loadedFor("Atlas Corp");
    choose(B.id);
    fireEvent.click(applyButton());
    expect(leaveTo).toHaveBeenCalledTimes(1);
    expect(leaveTo).toHaveBeenCalledWith(`/admin/risk-register?client=${B.id}`);
    noPostToActiveClient();

    // The new page load, as the browser would mount it.
    cleanup();
    vi.clearAllMocks();
    setUrl(`client=${B.id}`);
    lists([A, B], A.id);
    fetchRiskGate.mockResolvedValue(gate());
    fetchRiskRegisterLatest.mockResolvedValue(register({ client_id: B.id }));
    render(<RiskRegisterDashboard />);
    await loadedFor("Beacon LLC");
    expect(fetchRiskGate).toHaveBeenCalledWith(B.id);
    expect(fetchRiskGate).not.toHaveBeenCalledWith(A.id);
  });

  it("encodes the id it writes", async () => {
    const odd = summary("odd id/1", "Odd Org");
    lists([A, odd], A.id);
    render(<RiskRegisterDashboard />);
    await loadedFor("Atlas Corp");
    choose("odd id/1");
    fireEvent.click(applyButton());
    expect(leaveTo).toHaveBeenCalledWith(
      "/admin/risk-register?client=odd%20id%2F1",
    );
  });
});

describe("Apply from each starting state (§6.1)", () => {
  const STARTS: Array<[string, () => void, string | null]> = [
    ["unchosen", () => lists([A, B], null), STRING_4],
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
        setUrl(`client=${UNLISTED}`);
        lists([A, B], null);
      },
      STRING_17A,
    ],
    [
      "link_empty",
      () => {
        setUrl("client=");
        lists([A, B], null);
      },
      STRING_17B,
    ],
    ["chosen", () => lists([A, B], A.id), null],
  ];

  it.each(STARTS)("from %s", async (_state, arrange, startingLine) => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    arrange();
    render(<RiskRegisterDashboard />);
    // 1. The starting line is there, or absence below would prove nothing.
    if (startingLine === null) await headingFor("Atlas Corp");
    else expect(await screen.findByText(startingLine)).toBeInTheDocument();
    // 2. Choose B and Apply.
    choose(B.id);
    fireEvent.click(applyButton());
    expect(leaveTo).toHaveBeenCalledWith(`/admin/risk-register?client=${B.id}`);

    // 3. The new load: the header names B.
    cleanup();
    vi.clearAllMocks();
    setUrl(`client=${B.id}`);
    lists([A, B], null);
    fetchRiskGate.mockResolvedValue(gate());
    fetchRiskRegisterLatest.mockResolvedValue(register());
    render(<RiskRegisterDashboard />);
    await loadedFor("Beacon LLC");
    // 4. Only after the header: no starting line remains.
    for (const line of STARTING_LINES)
      expect(screen.queryByText(line)).toBeNull();
  });
});

describe("one client and a link that does not name it (§0h finding 6)", () => {
  it.each([
    [`client=${UNLISTED}`, STRING_17A],
    ["client=", STRING_17B],
  ])(
    "?%s: the placeholder shows, and choosing the client enables Apply",
    async (search, line) => {
      setUrl(search);
      lists([A], null);
      render(<RiskRegisterDashboard />);
      expect(await screen.findByText(line)).toBeInTheDocument();
      expect(picker().value).toBe("");
      expect(
        within(picker()).getByRole("option", { name: "— pick one —" }),
      ).toBeInTheDocument();
      expect(applyButton()).toBeDisabled();
      choose(A.id);
      expect(applyButton()).toBeEnabled();
      fireEvent.click(applyButton());
      expect(leaveTo).toHaveBeenCalledWith(
        `/admin/risk-register?client=${A.id}`,
      );
    },
  );
});

/** Each control that starts work, with the fixture that renders it. */
const CONTROLS: Array<[string, () => void, () => HTMLElement]> = [
  [
    "Regenerate",
    () => undefined,
    () => screen.getByRole("button", { name: "Regenerate" }),
  ],
  [
    "Export",
    () => undefined,
    () => screen.getByRole("button", { name: "Export XLSX / PDF / Word" }),
  ],
  [
    "Publish",
    () => undefined,
    () => screen.getByRole("button", { name: "Publish to client" }),
  ],
  [
    "a rating select",
    () => undefined,
    () =>
      screen.getByRole("combobox", { name: "Likelihood for Credential theft" }),
  ],
  [
    "the archive button",
    () =>
      fetchRiskGate.mockResolvedValue(
        gate({
          duplicate_inputs:
            "Two Zero Trust (CISA ZTMM 2.0) services would produce the same findings.",
          duplicate_services: [
            {
              service_id: "svc-1",
              title: "ZT one",
              started_at: "2026-10-01T00:00:00Z",
              status: "draft",
              version: 1,
            },
            {
              service_id: "svc-2",
              title: "ZT two",
              started_at: "2026-10-02T00:00:00Z",
              status: "draft",
              version: 1,
            },
          ],
        }),
      ),
    () => screen.getAllByRole("button", { name: /^Archive/ })[0],
  ],
];

describe("Apply locks the page (§3.3, rev 11 and 12)", () => {
  it.each(CONTROLS)(
    "%s is enabled before Apply and disabled after it",
    async (_name, arrange, control) => {
      arrange();
      lists([A, B], A.id);
      render(<RiskRegisterDashboard />);
      await loadedFor("Atlas Corp");
      // First ENABLED, so "disabled" below can only come from Apply.
      expect(control()).toBeEnabled();
      choose(B.id);
      fireEvent.click(applyButton());
      expect(control()).toBeDisabled();
      expect(picker()).toBeDisabled();
      expect(applyButton()).toBeDisabled();
      // Still A's page, saying where it is going.
      expect(
        screen.getByRole("heading", { name: "Risk Register for Atlas Corp" }),
      ).toBeInTheDocument();
      expect(screen.getByText(string18("Beacon LLC"))).toBeInTheDocument();
    },
  );

  it.each([
    ["unchosen", () => lists([A, B], null), STRING_4],
    [
      "link_unlisted",
      () => {
        setUrl(`client=${UNLISTED}`);
        lists([A, B], null);
      },
      STRING_17A,
    ],
  ])(
    "from %s, string 18 is the only line: the starting line is hidden",
    async (_state, arrange, line) => {
      arrange();
      render(<RiskRegisterDashboard />);
      expect(await screen.findByText(line)).toBeInTheDocument();
      choose(B.id);
      fireEvent.click(applyButton());
      expect(screen.getByText(string18("Beacon LLC"))).toBeInTheDocument();
      expect(screen.queryByText(line)).toBeNull();
    },
  );

  it("a page restored from the back/forward cache reloads; an ordinary pageshow does not", async () => {
    lists([A, B], A.id);
    render(<RiskRegisterDashboard />);
    await loadedFor("Atlas Corp");
    const show = (persisted: boolean) => {
      const ev = new Event("pageshow");
      Object.defineProperty(ev, "persisted", { value: persisted });
      window.dispatchEvent(ev);
    };
    show(false);
    expect(reloadPage).not.toHaveBeenCalled();
    show(true);
    expect(reloadPage).toHaveBeenCalledTimes(1);
  });
});

describe("work in flight locks the picker (§3.3)", () => {
  const PENDING: Array<[string, () => void, () => void]> = [
    [
      "Generate",
      () => generateRiskRegister.mockReturnValue(new Promise(() => undefined)),
      () => fireEvent.click(screen.getByRole("button", { name: "Regenerate" })),
    ],
    [
      "Export",
      () => exportRiskRegister.mockReturnValue(new Promise(() => undefined)),
      () =>
        fireEvent.click(
          screen.getByRole("button", { name: "Export XLSX / PDF / Word" }),
        ),
    ],
    [
      "Publish",
      () => publishRiskRegister.mockReturnValue(new Promise(() => undefined)),
      () =>
        fireEvent.click(
          screen.getByRole("button", { name: "Publish to client" }),
        ),
    ],
    [
      "a rating save",
      () => editRiskEntryRating.mockReturnValue(new Promise(() => undefined)),
      () =>
        fireEvent.change(
          screen.getByRole("combobox", {
            name: "Likelihood for Credential theft",
          }),
          { target: { value: "high" } },
        ),
    ],
  ];

  it.each(PENDING)(
    "a pending %s disables the picker and Apply",
    async (_name, hold, start) => {
      hold();
      lists([A, B], A.id);
      render(<RiskRegisterDashboard />);
      await loadedFor("Atlas Corp");
      choose(B.id);
      expect(applyButton()).toBeEnabled();
      act(() => start());
      await waitFor(() => expect(picker()).toBeDisabled());
      expect(applyButton()).toBeDisabled();
    },
  );

  it("is released once the work settles", async () => {
    let finish: (r: RiskRegister) => void = () => undefined;
    generateRiskRegister.mockReturnValue(
      new Promise<RiskRegister>((resolve) => {
        finish = resolve;
      }),
    );
    lists([A, B], A.id);
    render(<RiskRegisterDashboard />);
    await loadedFor("Atlas Corp");
    fireEvent.click(screen.getByRole("button", { name: "Regenerate" }));
    await waitFor(() => expect(picker()).toBeDisabled());
    await act(async () => finish(register({ version: 2 })));
    await waitFor(() => expect(picker()).toBeEnabled());
  });
});

describe("download links carry the picker's client (§3.2a)", () => {
  it("names A's id on A's page", async () => {
    lists([A, B], A.id);
    render(<RiskRegisterDashboard />);
    await loadedFor("Atlas Corp");
    expect(screen.getByRole("link", { name: /XLSX/ })).toHaveAttribute(
      "href",
      `/api/proxy/artifacts/art-x/download?client_id=${A.id}`,
    );
  });

  it("names B's id after the page loads for B, though the cookie names A", async () => {
    setUrl(`client=${B.id}`);
    lists([A, B], A.id);
    render(<RiskRegisterDashboard />);
    await loadedFor("Beacon LLC");
    expect(screen.getByRole("link", { name: /XLSX/ })).toHaveAttribute(
      "href",
      `/api/proxy/artifacts/art-x/download?client_id=${B.id}`,
    );
  });
});
