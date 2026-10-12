import "@testing-library/jest-dom/vitest";

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as clientReads from "@/lib/admin/client-reads";
import * as riskClient from "@/lib/risk/client";
import type { RiskGate } from "@/lib/risk/types";

import type * as React from "react";

import { RiskRegisterDashboard } from "./RiskRegisterDashboard";

/**
 * #554 R3 (the #808 review's F3): generating refuses while the approved ATT&CK
 * assessment's computed statuses await review, so the page says why with the
 * server's own sentence and does not offer a Generate whose only outcome is
 * that 409 -- the #556 catalog-mismatch precedent.
 */

vi.mock("@/lib/risk/client", () => ({
  describeRiskError: (e: unknown) => String(e),
  exportRiskRegister: vi.fn(),
  fetchRiskGate: vi.fn(),
  fetchRiskRegisterLatest: vi.fn(),
  generateRiskRegister: vi.fn(),
}));

// RR-2 (for #1121): the page takes its client from its own picker. The two
// reads are mocked where they live, with API-shaped bodies, so the real
// resolver chooses the client. The URL carries no ?client=.
vi.mock("next/navigation", () => ({
  usePathname: () => "/admin/risk-register",
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/lib/admin/client-reads", () => ({
  readClientList: vi.fn(),
  readActiveClient: vi.fn(),
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

/**
 * RR-2 (for #1121): `id` is the one listed client, named `name`, and the one
 * saved in this browser. The list is shaped like `AdminClientListResponse`.
 */
function mockPickedClient(id: string, name: string): void {
  vi.mocked(clientReads.readClientList).mockResolvedValue({
    clients: [
      {
        id,
        legal_name: name,
        dba_name: null,
        industry: null,
        size_band: null,
        intake_completed_at: null,
        created_at: "2026-10-01T00:00:00Z",
        archived_at: null,
        open_request_count: 0,
        total_request_count: 0,
      },
    ],
  });
  vi.mocked(clientReads.readActiveClient).mockResolvedValue({ active: id });
}

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
    // #737: required; the Inputs panel's rows.
    inputs: [],
    attack_computed_status_unreviewed: null,
    ...over,
  };
}

async function loaded(): Promise<void> {
  render(<RiskRegisterDashboard />);
  await waitFor(() => {
    // RR-2 (for #1121): the h1 names the client and renders before the
    // body has loaded, so the wait is for the body too.
    expect(
      screen.getByRole("heading", { name: /^Risk Register for / }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Loading…")).toBeNull();
  });
}

describe("RiskRegisterDashboard, an unreviewed ATT&CK input (#554 R3)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPickedClient("c1", "Atlas");
    vi.mocked(riskClient.fetchRiskRegisterLatest).mockResolvedValue(null);
  });

  it("no longer blocks Generate on unreviewed statuses (#737, option (b))", async () => {
    // DECLARED (#860, accepted). OLD: a banner with the refusal's sentence and
    // a disabled Generate. NEW: a draft may be generated; each affected entry
    // is labelled and publish refuses. Even a server still sending the old
    // sentence must not block the button.
    const sentence =
      "The Risk Register cannot be generated yet: 1 ATT&CK technique has a computed status that differs from the AI's suggestion and has not been reviewed. Review it in the ATT&CK Computed status review panel, then generate again.";
    vi.mocked(riskClient.fetchRiskGate).mockResolvedValue(
      gate({ attack_computed_status_unreviewed: sentence }),
    );
    await loaded();
    expect(
      screen.getByRole("button", { name: /^(Generate|Regenerate)$/ }),
    ).not.toBeDisabled();
    expect(screen.queryByTestId("risk-register-attack-unreviewed")).toBeNull();
  });

  it("offers Generate when nothing awaits review", async () => {
    vi.mocked(riskClient.fetchRiskGate).mockResolvedValue(gate());
    await loaded();
    expect(screen.queryByTestId("risk-register-attack-unreviewed")).toBeNull();
    expect(
      screen.getByRole("button", { name: /^(Generate|Regenerate)$/ }),
    ).not.toBeDisabled();
  });
});
