import "@testing-library/jest-dom/vitest";

import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import * as adminClient from "@/lib/admin/client";
import * as riskClient from "@/lib/risk/client";
import type { RiskGate } from "@/lib/risk/types";

import { RiskRegisterDashboard } from "./RiskRegisterDashboard";

/**
 * #896: the duplicate banner offers one archive button per service behind
 * the refusal, and confirming one reloads the gate. Copy from the advisor's
 * approval (#736 6042801745), never from the component.
 *
 * The refusal sentence itself is unchanged (advisor: the API message reaches
 * callers that are not this screen, so the remedy sits beneath it).
 */

vi.mock("@/lib/risk/client", () => ({
  describeRiskError: (e: unknown) => String(e),
  editRiskEntryRating: vi.fn(),
  publishRiskRegister: vi.fn(),
  exportRiskRegister: vi.fn(),
  fetchRiskGate: vi.fn(),
  fetchRiskRegisterLatest: vi.fn(),
  generateRiskRegister: vi.fn(),
  getActiveClientId: vi.fn(),
  getClientName: vi.fn(),
}));
vi.mock("@/lib/admin/client", () => ({ archiveService: vi.fn() }));

vi.mock("@/components/admin/RunAiGuard", () => ({
  RunAiGuard: ({
    children,
    onProceed,
  }: {
    children: (p: { onClick: () => void }) => React.ReactNode;
    onProceed: () => void;
  }) => children({ onClick: onProceed }),
}));

const fetchRiskGate = vi.mocked(riskClient.fetchRiskGate);
const fetchRiskRegisterLatest = vi.mocked(riskClient.fetchRiskRegisterLatest);
const getActiveClientId = vi.mocked(riskClient.getActiveClientId);
const getClientName = vi.mocked(riskClient.getClientName);
const archiveService = vi.mocked(adminClient.archiveService);

beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function showModal(): void {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function close(): void {
    this.open = false;
    this.dispatchEvent(new Event("close"));
  };
});

const DUPLICATE =
  "Two engaged services of the same kind would produce the same findings: ZT and ZT 2. The register cannot be generated while both are engaged.";
const LEAD = "Archive the one this register should not draw on:";

function gate(over: Partial<RiskGate> = {}): RiskGate {
  return {
    unlocked: true,
    has_attack: true,
    has_csf: false,
    has_zt: true,
    missing: [],
    not_finalized: [],
    synthesizable_missing: [],
    attack_catalog_mismatch: null,
    inputs: [],
    duplicate_inputs: null,
    duplicate_services: [],
    ...over,
  };
}

const DUPLICATE_GATE = gate({
  duplicate_inputs: DUPLICATE,
  duplicate_services: [
    { service_id: "svc-1", title: "ZT" },
    { service_id: "svc-2", title: "ZT 2" },
  ],
});

async function loaded(): Promise<void> {
  render(<RiskRegisterDashboard />);
  await waitFor(() =>
    expect(
      screen.getByRole("heading", { name: "Risk Register" }),
    ).toBeInTheDocument(),
  );
}

describe("RiskRegisterDashboard archive control (#896)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getActiveClientId.mockResolvedValue("c1");
    getClientName.mockResolvedValue("Client");
    fetchRiskRegisterLatest.mockResolvedValue(null);
  });

  it("offers an archive button for each service behind the refusal", async () => {
    fetchRiskGate.mockResolvedValue(DUPLICATE_GATE);
    await loaded();
    expect(
      screen.getByTestId("risk-register-duplicate-inputs"),
    ).toHaveTextContent(DUPLICATE);
    const archive = screen.getByTestId("risk-register-duplicate-archive");
    expect(archive).toHaveTextContent(LEAD);
    expect(
      within(archive).getByRole("button", { name: "Archive ZT" }),
    ).toBeInTheDocument();
    expect(
      within(archive).getByRole("button", { name: "Archive ZT 2" }),
    ).toBeInTheDocument();
  });

  it("offers no archive control when there is no duplicate", async () => {
    fetchRiskGate.mockResolvedValue(gate());
    await loaded();
    expect(screen.getByRole("button", { name: "Generate" })).toBeEnabled();
    expect(screen.queryByTestId("risk-register-duplicate-archive")).toBeNull();
    expect(screen.queryByText(LEAD)).toBeNull();
  });

  it("reloads the gate after an archive, which clears the refusal", async () => {
    fetchRiskGate
      .mockResolvedValueOnce(DUPLICATE_GATE)
      .mockResolvedValueOnce(gate());
    archiveService.mockResolvedValue(undefined);
    await loaded();
    expect(screen.getByRole("button", { name: "Generate" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Archive ZT 2" }));
    const dialog = screen.getByRole("dialog", { name: "Archive ZT 2?" });
    await act(async () => {
      fireEvent.click(
        within(dialog).getByRole("button", { name: "Yes, archive" }),
      );
    });

    expect(archiveService).toHaveBeenCalledWith("svc-2");
    await waitFor(() => expect(fetchRiskGate).toHaveBeenCalledTimes(2));
    expect(fetchRiskGate).toHaveBeenLastCalledWith("c1");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Generate" })).toBeEnabled(),
    );
    expect(screen.queryByTestId("risk-register-duplicate-inputs")).toBeNull();
    expect(screen.queryByTestId("risk-register-duplicate-archive")).toBeNull();
  });
});
