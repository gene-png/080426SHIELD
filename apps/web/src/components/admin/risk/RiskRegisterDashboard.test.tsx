import "@testing-library/jest-dom/vitest";

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as riskClient from "@/lib/risk/client";
import type { RiskGate, RiskRegister } from "@/lib/risk/types";

import { RiskRegisterDashboard } from "./RiskRegisterDashboard";

vi.mock("@/lib/risk/client", () => ({
  describeRiskError: (e: unknown) => String(e),
  exportRiskRegister: vi.fn(),
  fetchRiskGate: vi.fn(),
  fetchRiskRegisterLatest: vi.fn(),
  generateRiskRegister: vi.fn(),
  getActiveClientId: vi.fn(),
  getClientName: vi.fn(),
}));

const fetchRiskGate = vi.mocked(riskClient.fetchRiskGate);
const fetchRiskRegisterLatest = vi.mocked(riskClient.fetchRiskRegisterLatest);
const getActiveClientId = vi.mocked(riskClient.getActiveClientId);
const getClientName = vi.mocked(riskClient.getClientName);

function gate(over: Partial<RiskGate> = {}): RiskGate {
  return {
    unlocked: true,
    missing: [],
    not_finalized: [],
    synthesizable_missing: [],
    ...over,
  } as RiskGate;
}

function register(over: Partial<RiskRegister> = {}): RiskRegister {
  return {
    excluded_inputs: [],
    id: "r1",
    client_id: "c1",
    version: 1,
    generated_by: null,
    finalized_at: null,
    created_at: "2026-09-09T00:00:00Z",
    xlsx_artifact_id: null,
    pdf_artifact_id: null,
    docx_artifact_id: null,
    xlsx_filename: null,
    pdf_filename: null,
    docx_filename: null,
    entries: [],
    tier_counts: {},
    axis_counts: {},
    ...over,
  } as unknown as RiskRegister;
}

async function renderReady(): Promise<void> {
  render(<RiskRegisterDashboard />);
  await waitFor(() =>
    expect(
      screen.getByRole("heading", { name: "Risk Register" }),
    ).toBeInTheDocument(),
  );
}

/**
 * #237 review: `excluded_inputs` reached NO rendered surface.
 *
 * The provenance refusal was narrowed so an unapproved input that is not
 * required stops blocking — and the stated justification for narrowing it was
 * that the withheld set is disclosed. It was disclosed to nobody: five
 * occurrences in the tree, no consumer, not declared in the web type. A
 * consultant generated a register missing a whole service's findings and saw a
 * complete-looking page.
 *
 * These pin the banner. They do NOT claim it is durable: nothing about the
 * exclusion is persisted, so `latest` returns `[]` and the banner dies on
 * reload. That is #240 and the third test says so rather than leaving it to be
 * discovered.
 */
describe("RiskRegisterDashboard excluded-inputs disclosure", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getActiveClientId.mockResolvedValue("c1");
    getClientName.mockResolvedValue("Atlas");
    fetchRiskGate.mockResolvedValue(gate());
  });

  it("names the inputs a register was generated without", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(
      register({ excluded_inputs: ["the CSF assessment"] }),
    );
    await renderReady();
    const banner = screen.getByTestId("risk-register-excluded-inputs");
    // textContent, not innerText: innerText returns CSS-transformed text, so
    // asserting on it pins the styling rather than the copy.
    expect(banner.textContent).toMatch(/the CSF assessment/);
    expect(banner.textContent).toMatch(/not approved/);
  });

  it("says the exported documents do NOT carry the disclosure", async () => {
    // The banner must not imply the export is provenance-checked. It is not,
    // and that gap is #240.
    fetchRiskRegisterLatest.mockResolvedValue(
      register({ excluded_inputs: ["the Zero Trust assessment"] }),
    );
    await renderReady();
    expect(
      screen.getByTestId("risk-register-excluded-inputs").textContent,
    ).toMatch(/exported documents do not say so/i);
  });

  it("renders no banner when nothing was excluded", async () => {
    // The negative control. Without it, a banner that renders unconditionally
    // would satisfy both tests above.
    fetchRiskRegisterLatest.mockResolvedValue(
      register({ excluded_inputs: [] }),
    );
    await renderReady();
    expect(
      screen.queryByTestId("risk-register-excluded-inputs"),
    ).not.toBeInTheDocument();
  });
});
