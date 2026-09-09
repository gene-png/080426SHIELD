import "@testing-library/jest-dom/vitest";

import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
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

// The Generate control sits behind the offline-AI confirmation. Passing the
// child its own `onProceed` keeps these tests about the disclosure rather than
// about the guard, which has its own coverage.
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
const generateRiskRegister = vi.mocked(riskClient.generateRiskRegister);
const exportRiskRegister = vi.mocked(riskClient.exportRiskRegister);
const getActiveClientId = vi.mocked(riskClient.getActiveClientId);
const getClientName = vi.mocked(riskClient.getClientName);

/** No casts. If the wire type gains a field, these stop compiling — which is
 *  the point: the previous version cast the fixture and could therefore
 *  describe a payload the API never sends. */
function gate(over: Partial<RiskGate> = {}): RiskGate {
  return {
    unlocked: true,
    has_attack: true,
    has_csf: true,
    has_zt: true,
    missing: [],
    not_finalized: [],
    synthesizable_missing: [],
    ...over,
  };
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
    action_counts: {},
    ...over,
  };
}

const BANNER = "risk-register-excluded-inputs";

async function loaded(): Promise<void> {
  render(<RiskRegisterDashboard />);
  await waitFor(() =>
    expect(
      screen.getByRole("heading", { name: "Risk Register" }),
    ).toBeInTheDocument(),
  );
}

/**
 * #237 review round 2: `excluded_inputs` reached no surface. Round 3: the
 * banner that fixed it was erased by the export it warns about.
 *
 * **These tests drive `generateRiskRegister`, which is the ONLY producer of a
 * non-empty withheld set.** The first version drove `fetchRiskRegisterLatest`,
 * which this PR's own type doc says "always returns `[]`" — so every test
 * exercised the one path that can never carry the field, and the export defect
 * was invisible to a green suite. A fixture describing a response the API
 * cannot emit is the defect this branch exists to end, committed in the tests
 * for it.
 */
describe("RiskRegisterDashboard excluded-inputs disclosure", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getActiveClientId.mockResolvedValue("c1");
    getClientName.mockResolvedValue("Atlas");
    fetchRiskGate.mockResolvedValue(gate());
    fetchRiskRegisterLatest.mockResolvedValue(null);
  });

  it("names the inputs a register was generated without", async () => {
    generateRiskRegister.mockResolvedValue(
      register({ excluded_inputs: ["the CSF assessment"] }),
    );
    await loaded();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Generate" }));
    });

    const banner = await screen.findByTestId(BANNER);
    // textContent, not innerText: innerText returns CSS-transformed text, so
    // asserting on it pins styling rather than copy.
    expect(banner.textContent).toMatch(/the CSF assessment/);
    expect(banner.textContent).toMatch(/not approved/);
    expect(banner.textContent).toMatch(/exported documents do not say so/i);
  });

  it("KEEPS the disclosure after Export — the action it warns about", async () => {
    // The regression this file exists for. `export` returns the register
    // WITHOUT `excluded_inputs` (the schema defaults it to `[]`), so assigning
    // component state from that response erased the banner at exactly the
    // moment the deliverable was produced. The withheld set describes what the
    // register was BUILT from; no later response can revise it.
    generateRiskRegister.mockResolvedValue(
      register({ excluded_inputs: ["the Zero Trust assessment"] }),
    );
    exportRiskRegister.mockResolvedValue(
      register({ excluded_inputs: [], finalized_at: "2026-09-09T01:00:00Z" }),
    );
    await loaded();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Generate" }));
    });
    await screen.findByTestId(BANNER);

    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "Export XLSX / PDF / Word" }),
      );
    });
    await waitFor(() => expect(exportRiskRegister).toHaveBeenCalled());

    expect(screen.getByTestId(BANNER).textContent).toMatch(
      /the Zero Trust assessment/,
    );
  });

  it("renders no banner when nothing was excluded", async () => {
    // Negative control. Without it, a banner rendered unconditionally would
    // satisfy both tests above.
    generateRiskRegister.mockResolvedValue(register({ excluded_inputs: [] }));
    await loaded();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Generate" }));
    });
    await waitFor(() => expect(generateRiskRegister).toHaveBeenCalled());
    expect(screen.queryByTestId(BANNER)).not.toBeInTheDocument();
  });

  it("shows no banner before anything is generated", async () => {
    // `latest` returns `[]` for a pre-existing register — the stated #240
    // limitation. Pinned so the limitation is visible rather than discovered.
    fetchRiskRegisterLatest.mockResolvedValue(
      register({ excluded_inputs: [] }),
    );
    await loaded();
    expect(screen.queryByTestId(BANNER)).not.toBeInTheDocument();
  });
});
