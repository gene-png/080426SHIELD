import "@testing-library/jest-dom/vitest";

import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RunAiGuard } from "@/components/admin/RunAiGuard";
import * as clientReads from "@/lib/admin/client-reads";
import * as riskClient from "@/lib/risk/client";
import type { RiskGate, RiskRegister } from "@/lib/risk/types";

import { RiskRegisterDashboard } from "./RiskRegisterDashboard";

/**
 * RR-2 (for #1121), design note §3.3 and §0i finding 1: a click `RunAiGuard`
 * is holding for the AI status, or its offline prompt, is work that has not
 * started yet, so it locks the picker like work in flight. The REAL guard
 * runs here; only `fetch` stands in for `/api/proxy/admin/ai-status`.
 */

vi.mock("next/navigation", () => ({
  usePathname: () => "/admin/risk-register",
  useSearchParams: () => new URLSearchParams(),
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

const OFFLINE_STATUS = {
  mode: "fixture",
  provider: "none",
  model: "none",
  ready: false,
  detail: "No key is loaded.",
  can_configure: true,
  key_source: "none",
  serves: "offline",
};

function gate(): RiskGate {
  return {
    unlocked: true,
    has_attack: true,
    has_csf: true,
    has_zt: true,
    // RR-1 (for #1122): the selection block's rows. With none, Generate
    // stays disabled (design note §3.4).
    eligible: [
      {
        kind: "attack",
        service_id: "svc-attack",
        title: "ATT&CK",
        framework: null,
        label: "ATT&CK coverage",
      },
      {
        kind: "csf",
        service_id: "svc-csf",
        title: "CSF",
        framework: null,
        label: "NIST CSF",
      },
      {
        kind: "zt",
        service_id: "svc-zt",
        title: "ZT",
        framework: "cisa_ztmm_2_0",
        label: "Zero Trust (CISA ZTMM 2.0)",
      },
    ],
    ineligible: [],
    missing: [],
    not_finalized: [],
    synthesizable_missing: [],
    attack_catalog_mismatch: null,
    inputs: [],
  };
}

let releaseStatus: (body: unknown) => void = () => undefined;

function holdAiStatus(): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      if (String(url).includes("/api/proxy/admin/ai-status")) {
        return new Promise((resolve) => {
          releaseStatus = (body) =>
            resolve(
              new Response(JSON.stringify(body), {
                status: 200,
                headers: { "Content-Type": "application/json" },
              }),
            );
        });
      }
      throw new Error(`unexpected fetch ${String(url)}`);
    }),
  );
}

function picker(): HTMLElement {
  return screen.getByRole("combobox", { name: "Client for this page" });
}
function applyButton(): HTMLElement {
  return screen.getByRole("button", { name: "Show this client" });
}

beforeEach(() => {
  vi.clearAllMocks();
  window.sessionStorage.clear();
  window.localStorage.clear();
  holdAiStatus();
  vi.mocked(clientReads.readClientList).mockResolvedValue({ clients: [A, B] });
  vi.mocked(clientReads.readActiveClient).mockResolvedValue({ active: A.id });
  vi.mocked(riskClient.fetchRiskGate).mockResolvedValue(gate());
  vi.mocked(riskClient.fetchRiskRegisterLatest).mockResolvedValue(
    null as unknown as RiskRegister,
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function loadedWithBChosen(): Promise<void> {
  render(<RiskRegisterDashboard />);
  await screen.findByText(/· not yet generated/);
  fireEvent.change(picker(), { target: { value: B.id } });
  expect(applyButton()).toBeEnabled();
}

describe("RunAiGuard busy locks the picker (§3.3)", () => {
  it("a held click, then the offline prompt, keep the picker and Apply disabled; Cancel releases them", async () => {
    await loadedWithBChosen();
    fireEvent.click(screen.getByRole("button", { name: "Generate" }));
    // The status is still loading, so the guard HOLDS the click.
    await waitFor(() => expect(applyButton()).toBeDisabled());
    expect(picker()).toBeDisabled();

    await act(async () => releaseStatus(OFFLINE_STATUS));
    // Not ready and offline-serving: the prompt opens. Still locked.
    expect(
      await screen.findByRole("button", { name: "Continue offline" }),
    ).toBeInTheDocument();
    expect(applyButton()).toBeDisabled();
    expect(picker()).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(applyButton()).toBeEnabled());
    expect(picker()).toBeEnabled();
  });

  it("'Continue offline' with Generate pending stays locked until the Generate settles", async () => {
    let finish: (r: RiskRegister) => void = () => undefined;
    vi.mocked(riskClient.generateRiskRegister).mockReturnValue(
      new Promise<RiskRegister>((resolve) => {
        finish = resolve;
      }),
    );
    await loadedWithBChosen();
    fireEvent.click(screen.getByRole("button", { name: "Generate" }));
    await act(async () => releaseStatus(OFFLINE_STATUS));
    fireEvent.click(
      await screen.findByRole("button", { name: "Continue offline" }),
    );
    await waitFor(() =>
      expect(vi.mocked(riskClient.generateRiskRegister)).toHaveBeenCalled(),
    );
    expect(applyButton()).toBeDisabled();
    await act(async () => finish(null as unknown as RiskRegister));
    await waitFor(() => expect(applyButton()).toBeEnabled());
  });
});

describe("RunAiGuard's onBusyChange (§0j finding 7)", () => {
  it("says false when it unmounts while holding a click", async () => {
    const onBusyChange = vi.fn();
    const { unmount } = render(
      <RunAiGuard onProceed={() => undefined} onBusyChange={onBusyChange}>
        {({ onClick }) => (
          <button type="button" onClick={onClick}>
            Run
          </button>
        )}
      </RunAiGuard>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Run" }));
    await waitFor(() => expect(onBusyChange).toHaveBeenLastCalledWith(true));
    unmount();
    expect(onBusyChange).toHaveBeenLastCalledWith(false);
  });
});
