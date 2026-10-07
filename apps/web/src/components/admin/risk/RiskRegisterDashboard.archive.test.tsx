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

import * as riskClient from "@/lib/risk/client";
import type { RiskDuplicateService, RiskGate } from "@/lib/risk/types";

import { RiskRegisterDashboard } from "./RiskRegisterDashboard";

/**
 * #896: the duplicate banner offers one archive button per service behind
 * the refusal, and the dialog reloads the gate whatever the outcome (review
 * B2). Copy from the advisor's approvals (#736 6042801745, 6046491381), never
 * from the component.
 *
 * The refusal sentence itself is unchanged (advisor: the API message reaches
 * callers that are not this screen, so the remedy sits beneath it).
 */

vi.mock("@/lib/risk/client", () => ({
  archiveDuplicateService: vi.fn(),
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
const archive = vi.mocked(riskClient.archiveDuplicateService);

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
// The server's sentence (#736 6046491381, last sentence moved to the screen by
// 6047873969); the screen's lines are written out at each assertion.
const NOT_IN_GROUP =
  "ZT 2 is no longer one of several engaged services of the same kind, so it was not archived.";

function svc(
  service_id: string,
  title: string,
  over: Partial<RiskDuplicateService> = {},
): RiskDuplicateService {
  return {
    service_id,
    title,
    started_at: "2026-10-03T12:00:00Z",
    status: "draft",
    version: 1,
    ...over,
  };
}

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
  duplicate_services: [svc("svc-1", "ZT"), svc("svc-2", "ZT 2")],
});

async function loaded(): Promise<void> {
  render(<RiskRegisterDashboard />);
  await waitFor(() =>
    expect(
      screen.getByRole("heading", { name: "Risk Register" }),
    ).toBeInTheDocument(),
  );
}

async function confirmIn(dialog: HTMLElement): Promise<void> {
  await act(async () => {
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Yes, archive" }),
    );
  });
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
    const banner = screen.getByTestId("risk-register-duplicate-archive");
    expect(banner).toHaveTextContent(LEAD);
    expect(
      within(banner).getByRole("button", { name: "Archive ZT" }),
    ).toBeInTheDocument();
    expect(
      within(banner).getByRole("button", { name: "Archive ZT 2" }),
    ).toBeInTheDocument();
  });

  it("offers no archive control when there is no duplicate", async () => {
    fetchRiskGate.mockResolvedValue(gate());
    await loaded();
    expect(screen.getByRole("button", { name: "Generate" })).toBeEnabled();
    expect(screen.queryByTestId("risk-register-duplicate-archive")).toBeNull();
    expect(screen.queryByText(LEAD)).toBeNull();
  });

  it("with two EQUAL titles, archives the service whose button was pressed", async () => {
    // B1: both default title paths give a second service the first one's
    // title. The second button must reach the second service's id.
    fetchRiskGate.mockResolvedValue(
      gate({
        duplicate_inputs: DUPLICATE,
        duplicate_services: [
          svc("svc-released", "Acme — Zero Trust", {
            status: "released",
            version: 2,
          }),
          svc("svc-draft", "Acme — Zero Trust"),
        ],
      }),
    );
    archive.mockResolvedValue(undefined);
    await loaded();
    const buttons = within(
      screen.getByTestId("risk-register-duplicate-archive"),
    ).getAllByRole("button", { name: "Archive Acme — Zero Trust" });
    expect(buttons).toHaveLength(2);
    // What tells them apart (advisor, #736 6046898402), written out by hand.
    expect(buttons[0]).toHaveAccessibleDescription(
      "Started 3 Oct 2026, version 2, released",
    );
    expect(buttons[1]).toHaveAccessibleDescription(
      "Started 3 Oct 2026, version 1, in progress (draft)",
    );
    fireEvent.click(buttons[1]);
    const dialog = screen.getByRole("dialog", {
      name: "Archive Acme — Zero Trust?",
    });
    expect(
      within(dialog).getByText(
        "Started 3 Oct 2026, version 1, in progress (draft)",
      ),
    ).toBeInTheDocument();
    await confirmIn(dialog);
    expect(archive).toHaveBeenCalledWith("c1", "svc-draft");
  });

  it("reloads the gate after an archive, which clears the refusal", async () => {
    fetchRiskGate
      .mockResolvedValueOnce(DUPLICATE_GATE)
      .mockResolvedValueOnce(gate());
    archive.mockResolvedValue(undefined);
    await loaded();
    expect(screen.getByRole("button", { name: "Generate" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Archive ZT 2" }));
    await confirmIn(screen.getByRole("dialog", { name: "Archive ZT 2?" }));

    expect(archive).toHaveBeenCalledWith("c1", "svc-2");
    await waitFor(() => expect(fetchRiskGate).toHaveBeenCalledTimes(2));
    expect(fetchRiskGate).toHaveBeenLastCalledWith("c1");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Generate" })).toBeEnabled(),
    );
    expect(screen.queryByTestId("risk-register-duplicate-inputs")).toBeNull();
    expect(screen.queryByTestId("risk-register-duplicate-archive")).toBeNull();
  });

  it("two tabs: the stale archive is refused, the list refreshes, and the message stays", async () => {
    // Another tab archived ZT already. This tab still shows both, presses
    // Archive ZT 2, and the server refuses: ZT 2 is now the only one.
    fetchRiskGate
      .mockResolvedValueOnce(DUPLICATE_GATE)
      .mockResolvedValueOnce(gate());
    archive.mockRejectedValue({
      status: 409,
      payload: {
        error: {
          code: 409,
          reason: "service_not_in_duplicate_group",
          message: NOT_IN_GROUP,
        },
      },
    });
    await loaded();

    fireEvent.click(screen.getByRole("button", { name: "Archive ZT 2" }));
    const dialog = screen.getByRole("dialog", { name: "Archive ZT 2?" });
    await confirmIn(dialog);

    await waitFor(() => expect(fetchRiskGate).toHaveBeenCalledTimes(2));
    // Positive first: the refreshed page offers Generate...
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Generate" })).toBeEnabled(),
    );
    // ...the banner and its buttons are gone, and the dialog that said so is
    // still open with the server's sentence.
    expect(screen.queryByTestId("risk-register-duplicate-archive")).toBeNull();
    const still = screen.getByRole("dialog", { name: "Archive ZT 2?" });
    // F1: the reload succeeded, so the screen says the list was refreshed.
    expect(within(still).getByRole("alert").textContent).toBe(
      `${NOT_IN_GROUP} The list has been refreshed.`,
    );
  });

  it("F1: when the reload after a refusal fails, it says to reload the page", async () => {
    // Review round 2, F1 (advisor, #736 6047873969). The archive is refused
    // AND the gate cannot be re-read: the banner still shows the old list, so
    // nothing may claim the list was refreshed.
    fetchRiskGate
      .mockResolvedValueOnce(DUPLICATE_GATE)
      .mockRejectedValueOnce(new Error("gate down"));
    archive.mockRejectedValue({
      status: 409,
      payload: {
        error: {
          code: 409,
          reason: "service_not_in_duplicate_group",
          message: NOT_IN_GROUP,
        },
      },
    });
    await loaded();
    fireEvent.click(screen.getByRole("button", { name: "Archive ZT 2" }));
    const dialog = screen.getByRole("dialog", { name: "Archive ZT 2?" });
    await confirmIn(dialog);

    await waitFor(() => expect(fetchRiskGate).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(within(dialog).getByRole("alert").textContent).toBe(
        `${NOT_IN_GROUP} The list could not be refreshed. Reload the page before trying again.`,
      ),
    );
    // The old list is still on screen: the reload did not replace it.
    expect(
      screen.getByTestId("risk-register-duplicate-archive"),
    ).toBeInTheDocument();
  });

  it("R3-1/R3-2: a dismiss attempt while archiving changes nothing, and the buttons keep working", async () => {
    // Round 3. While "Archiving…" a backdrop click, Esc and a forced close
    // used to close the native dialog while the dashboard still held its
    // target, so no button could open it again until a page reload.
    fetchRiskGate.mockResolvedValue(DUPLICATE_GATE);
    let fail: (e: unknown) => void = () => {};
    archive.mockReturnValue(
      new Promise<void>((_resolve, reject) => {
        fail = reject;
      }),
    );
    await loaded();
    fireEvent.click(screen.getByRole("button", { name: "Archive ZT 2" }));
    const dialog = screen.getByRole("dialog", {
      name: "Archive ZT 2?",
    }) as HTMLDialogElement;
    await confirmIn(dialog);

    fireEvent.click(dialog); // the backdrop
    dialog.dispatchEvent(new Event("cancel", { cancelable: true })); // Esc
    dialog.close(); // a close the browser forces anyway
    expect(dialog.open).toBe(true);

    await act(async () => {
      fail({ status: 502, payload: null });
    });
    await waitFor(() =>
      expect(within(dialog).getByRole("alert").textContent).toBe(
        "The service could not be archived. Nothing was changed.",
      ),
    );
    expect(dialog.open).toBe(true);

    // Closed the ordinary way, the buttons open it again...
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(dialog.open).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Archive ZT" }));
    expect(
      screen.getByRole("dialog", { name: "Archive ZT?" }),
    ).toBeInTheDocument();
    // ...and (R3-2) for the SAME service, with no line left from before.
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(screen.getByRole("button", { name: "Archive ZT 2" }));
    const reopened = screen.getByRole("dialog", {
      name: "Archive ZT 2?",
    }) as HTMLDialogElement;
    expect(reopened.open).toBe(true);
    expect(within(reopened).queryByRole("alert")).toBeNull();
  });
});
