import "@testing-library/jest-dom/vitest";

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

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
    attack_computed_status_unreviewed: null,
    ...over,
  };
}

async function loaded(): Promise<void> {
  render(<RiskRegisterDashboard />);
  await waitFor(() =>
    expect(
      screen.getByRole("heading", { name: "Risk Register" }),
    ).toBeInTheDocument(),
  );
}

describe("RiskRegisterDashboard, an unreviewed ATT&CK input (#554 R3)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(riskClient.getActiveClientId).mockResolvedValue("c1");
    vi.mocked(riskClient.getClientName).mockResolvedValue("Atlas");
    vi.mocked(riskClient.fetchRiskRegisterLatest).mockResolvedValue(null);
  });

  it("says why, in the refusal's own sentence, and offers no Generate", async () => {
    const sentence =
      "The Risk Register cannot be generated yet: 1 ATT&CK technique has a computed status that differs from the AI's suggestion and has not been reviewed. Review it in the ATT&CK Computed status review panel, then generate again.";
    vi.mocked(riskClient.fetchRiskGate).mockResolvedValue(
      gate({ attack_computed_status_unreviewed: sentence }),
    );
    await loaded();
    const banner = await screen.findByTestId("risk-register-attack-unreviewed");
    expect(banner.textContent).toContain(sentence);
    expect(
      screen.getByRole("button", { name: /^(Generate|Regenerate)$/ }),
    ).toBeDisabled();
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
