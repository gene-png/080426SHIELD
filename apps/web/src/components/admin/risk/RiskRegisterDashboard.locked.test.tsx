import "@testing-library/jest-dom/vitest";

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as riskClient from "@/lib/risk/client";
import type { RiskGate } from "@/lib/risk/types";

import { RiskRegisterDashboard } from "./RiskRegisterDashboard";

/**
 * #1081, ruling (ii): the locked page renders the gate's `locked_message`,
 * the approved copy the API composes per missing kind (#736 6115773247; (B)
 * for CSF/ZT replaced in #1081 comment 6116102972). Written out here, never
 * imported. The title is unchanged.
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

const fetchRiskGate = vi.mocked(riskClient.fetchRiskGate);
const fetchRiskRegisterLatest = vi.mocked(riskClient.fetchRiskRegisterLatest);
const getActiveClientId = vi.mocked(riskClient.getActiveClientId);
const getClientName = vi.mocked(riskClient.getClientName);

const MESSAGE =
  "Acme has no MITRE ATT&CK Coverage Mapping service. A client adds it by selecting MITRE ATT&CK Coverage Mapping in the Services step of its intake; there is no control here to add it. Acme has no NIST CSF 2.0 Assessment or Zero Trust service. The client can add one by selecting it in the Services step of its intake, or by starting a self-assessment from My Assessments. A draft assessment is enough to generate a draft register; approve the assessments before you publish it.";

function lockedGate(over: Partial<RiskGate> = {}): RiskGate {
  return {
    unlocked: false,
    has_attack: false,
    has_csf: false,
    has_zt: false,
    missing: [
      "a MITRE ATT&CK coverage mapping",
      "a CSF or Zero Trust assessment",
    ],
    not_finalized: [],
    synthesizable_missing: [],
    attack_catalog_mismatch: null,
    inputs: [],
    duplicate_inputs: null,
    duplicate_services: [],
    locked_inputs: [
      {
        requirement: "attack",
        state: "no_service",
        service_kind: null,
        sentence: "(not rendered on its own)",
      },
    ],
    locked_message: MESSAGE,
    ...over,
  };
}

describe("RiskRegisterDashboard, locked (#1081)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getActiveClientId.mockResolvedValue("cid-1");
    getClientName.mockResolvedValue("Acme");
    fetchRiskRegisterLatest.mockResolvedValue(null);
  });

  it("renders the gate's locked message under the unchanged title", async () => {
    fetchRiskGate.mockResolvedValue(lockedGate());
    render(<RiskRegisterDashboard />);
    await waitFor(() =>
      expect(screen.getByText("Risk Register is locked")).toBeInTheDocument(),
    );
    expect(screen.getByText(MESSAGE)).toBeInTheDocument();
    // Then the absences: the old sentence, and any Generate.
    expect(screen.queryByText(/first complete/)).toBeNull();
    expect(
      screen.queryByRole("button", { name: /Generate|Regenerate/ }),
    ).toBeNull();
  });

  it("falls back to naming what is missing when an older API sends no message", async () => {
    fetchRiskGate.mockResolvedValue(
      lockedGate({ locked_inputs: undefined, locked_message: undefined }),
    );
    render(<RiskRegisterDashboard />);
    await waitFor(() =>
      expect(screen.getByText("Risk Register is locked")).toBeInTheDocument(),
    );
    expect(
      screen.getByText(
        "To synthesise risks for Acme, first complete: a MITRE ATT&CK coverage mapping; a CSF or Zero Trust assessment.",
      ),
    ).toBeInTheDocument();
  });
});
