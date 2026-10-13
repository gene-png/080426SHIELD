import "@testing-library/jest-dom/vitest";

import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as clientReads from "@/lib/admin/client-reads";
import * as riskClient from "@/lib/risk/client";
import type { RiskGate, RiskSelectableService } from "@/lib/risk/types";

import type * as React from "react";

import { RiskRegisterDashboard } from "./RiskRegisterDashboard";

/**
 * RR-1 (for #1122): Matrix A, page, every row, from the design note rev 12
 * §2a (sha256 d17b3aed64128954…). The rows below were extracted from that table
 * by script, not written by hand, and every expected string is §8's copy:
 * 2 ("{label}, required"), 5a, 17 and 18. LOCKED rows are asserted locked:
 * no selection block and no Generate.
 */

vi.mock("@/lib/risk/client", () => ({
  describeRiskError: (e: unknown) => String(e),
  exportRiskRegister: vi.fn(),
  fetchRiskGate: vi.fn(),
  fetchRiskRegisterLatest: vi.fn(),
  generateRiskRegister: vi.fn(),
}));
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

type Cell = "none" | "no_record" | "eligible";
interface Row {
  id: string;
  csf: Cell;
  cisa: Cell;
  dod: Cell;
  locked: boolean;
  csfBox?: string;
  ztBox?: string;
  ztFramework?: "cisa_ztmm_2_0" | "dod_ztra" | null;
  generate?: "enabled" | "disabled";
  copy?: "5a" | "17" | null;
  disabledRows?: string[];
}

// prettier-ignore
const MATRIX_A_PAGE: Row[] = [
  {"id": "A1", "csf": "none", "cisa": "none", "dod": "none", "locked": true},
  {"id": "A2", "csf": "none", "cisa": "none", "dod": "no_record", "locked": true},
  {"id": "A3", "csf": "none", "cisa": "none", "dod": "eligible", "locked": false, "csfBox": "n/a", "ztBox": "ticked (required)", "ztFramework": null, "generate": "enabled", "copy": null, "disabledRows": []},
  {"id": "A4", "csf": "none", "cisa": "no_record", "dod": "none", "locked": true},
  {"id": "A5", "csf": "none", "cisa": "no_record", "dod": "no_record", "locked": true},
  {"id": "A6", "csf": "none", "cisa": "no_record", "dod": "eligible", "locked": false, "csfBox": "n/a", "ztBox": "ticked (required)", "ztFramework": null, "generate": "enabled", "copy": null, "disabledRows": ["Zero Trust (CISA ZTMM 2.0)"]},
  {"id": "A7", "csf": "none", "cisa": "eligible", "dod": "none", "locked": false, "csfBox": "n/a", "ztBox": "ticked (required)", "ztFramework": null, "generate": "enabled", "copy": null, "disabledRows": []},
  {"id": "A8", "csf": "none", "cisa": "eligible", "dod": "no_record", "locked": false, "csfBox": "n/a", "ztBox": "ticked (required)", "ztFramework": null, "generate": "enabled", "copy": null, "disabledRows": ["Zero Trust (DoD ZT Reference Architecture)"]},
  {"id": "A9", "csf": "none", "cisa": "eligible", "dod": "eligible", "locked": false, "csfBox": "n/a", "ztBox": "ticked (required)", "ztFramework": null, "generate": "disabled", "copy": "17", "disabledRows": []},
  {"id": "A10", "csf": "none", "cisa": "eligible", "dod": "eligible", "locked": false, "csfBox": "n/a", "ztBox": "ticked (required)", "ztFramework": "cisa_ztmm_2_0", "generate": "enabled", "copy": null, "disabledRows": []},
  {"id": "A11", "csf": "none", "cisa": "eligible", "dod": "eligible", "locked": false, "csfBox": "n/a", "ztBox": "ticked (required)", "ztFramework": "dod_ztra", "generate": "enabled", "copy": null, "disabledRows": []},
  {"id": "A12", "csf": "no_record", "cisa": "none", "dod": "none", "locked": true},
  {"id": "A13", "csf": "no_record", "cisa": "none", "dod": "no_record", "locked": true},
  {"id": "A14", "csf": "no_record", "cisa": "none", "dod": "eligible", "locked": false, "csfBox": "n/a", "ztBox": "ticked (required)", "ztFramework": null, "generate": "enabled", "copy": null, "disabledRows": ["NIST CSF"]},
  {"id": "A15", "csf": "no_record", "cisa": "no_record", "dod": "none", "locked": true},
  {"id": "A16", "csf": "no_record", "cisa": "no_record", "dod": "no_record", "locked": true},
  {"id": "A17", "csf": "no_record", "cisa": "no_record", "dod": "eligible", "locked": false, "csfBox": "n/a", "ztBox": "ticked (required)", "ztFramework": null, "generate": "enabled", "copy": null, "disabledRows": ["NIST CSF", "Zero Trust (CISA ZTMM 2.0)"]},
  {"id": "A18", "csf": "no_record", "cisa": "eligible", "dod": "none", "locked": false, "csfBox": "n/a", "ztBox": "ticked (required)", "ztFramework": null, "generate": "enabled", "copy": null, "disabledRows": ["NIST CSF"]},
  {"id": "A19", "csf": "no_record", "cisa": "eligible", "dod": "no_record", "locked": false, "csfBox": "n/a", "ztBox": "ticked (required)", "ztFramework": null, "generate": "enabled", "copy": null, "disabledRows": ["NIST CSF", "Zero Trust (DoD ZT Reference Architecture)"]},
  {"id": "A20", "csf": "no_record", "cisa": "eligible", "dod": "eligible", "locked": false, "csfBox": "n/a", "ztBox": "ticked (required)", "ztFramework": null, "generate": "disabled", "copy": "17", "disabledRows": ["NIST CSF"]},
  {"id": "A21", "csf": "no_record", "cisa": "eligible", "dod": "eligible", "locked": false, "csfBox": "n/a", "ztBox": "ticked (required)", "ztFramework": "cisa_ztmm_2_0", "generate": "enabled", "copy": null, "disabledRows": ["NIST CSF"]},
  {"id": "A22", "csf": "no_record", "cisa": "eligible", "dod": "eligible", "locked": false, "csfBox": "n/a", "ztBox": "ticked (required)", "ztFramework": "dod_ztra", "generate": "enabled", "copy": null, "disabledRows": ["NIST CSF"]},
  {"id": "A23", "csf": "eligible", "cisa": "none", "dod": "none", "locked": false, "csfBox": "ticked (required)", "ztBox": "n/a", "ztFramework": null, "generate": "enabled", "copy": null, "disabledRows": []},
  {"id": "A24", "csf": "eligible", "cisa": "none", "dod": "no_record", "locked": false, "csfBox": "ticked (required)", "ztBox": "n/a", "ztFramework": null, "generate": "enabled", "copy": null, "disabledRows": ["Zero Trust (DoD ZT Reference Architecture)"]},
  {"id": "A25", "csf": "eligible", "cisa": "none", "dod": "eligible", "locked": false, "csfBox": "unticked", "ztBox": "unticked", "ztFramework": null, "generate": "disabled", "copy": "5a", "disabledRows": []},
  {"id": "A26", "csf": "eligible", "cisa": "none", "dod": "eligible", "locked": false, "csfBox": "unticked", "ztBox": "ticked", "ztFramework": null, "generate": "enabled", "copy": null, "disabledRows": []},
  {"id": "A27", "csf": "eligible", "cisa": "none", "dod": "eligible", "locked": false, "csfBox": "ticked", "ztBox": "unticked", "ztFramework": null, "generate": "enabled", "copy": null, "disabledRows": []},
  {"id": "A28", "csf": "eligible", "cisa": "none", "dod": "eligible", "locked": false, "csfBox": "ticked", "ztBox": "ticked", "ztFramework": null, "generate": "enabled", "copy": null, "disabledRows": []},
  {"id": "A29", "csf": "eligible", "cisa": "no_record", "dod": "none", "locked": false, "csfBox": "ticked (required)", "ztBox": "n/a", "ztFramework": null, "generate": "enabled", "copy": null, "disabledRows": ["Zero Trust (CISA ZTMM 2.0)"]},
  {"id": "A30", "csf": "eligible", "cisa": "no_record", "dod": "no_record", "locked": false, "csfBox": "ticked (required)", "ztBox": "n/a", "ztFramework": null, "generate": "enabled", "copy": null, "disabledRows": ["Zero Trust (CISA ZTMM 2.0)", "Zero Trust (DoD ZT Reference Architecture)"]},
  {"id": "A31", "csf": "eligible", "cisa": "no_record", "dod": "eligible", "locked": false, "csfBox": "unticked", "ztBox": "unticked", "ztFramework": null, "generate": "disabled", "copy": "5a", "disabledRows": ["Zero Trust (CISA ZTMM 2.0)"]},
  {"id": "A32", "csf": "eligible", "cisa": "no_record", "dod": "eligible", "locked": false, "csfBox": "unticked", "ztBox": "ticked", "ztFramework": null, "generate": "enabled", "copy": null, "disabledRows": ["Zero Trust (CISA ZTMM 2.0)"]},
  {"id": "A33", "csf": "eligible", "cisa": "no_record", "dod": "eligible", "locked": false, "csfBox": "ticked", "ztBox": "unticked", "ztFramework": null, "generate": "enabled", "copy": null, "disabledRows": ["Zero Trust (CISA ZTMM 2.0)"]},
  {"id": "A34", "csf": "eligible", "cisa": "no_record", "dod": "eligible", "locked": false, "csfBox": "ticked", "ztBox": "ticked", "ztFramework": null, "generate": "enabled", "copy": null, "disabledRows": ["Zero Trust (CISA ZTMM 2.0)"]},
  {"id": "A35", "csf": "eligible", "cisa": "eligible", "dod": "none", "locked": false, "csfBox": "unticked", "ztBox": "unticked", "ztFramework": null, "generate": "disabled", "copy": "5a", "disabledRows": []},
  {"id": "A36", "csf": "eligible", "cisa": "eligible", "dod": "none", "locked": false, "csfBox": "unticked", "ztBox": "ticked", "ztFramework": null, "generate": "enabled", "copy": null, "disabledRows": []},
  {"id": "A37", "csf": "eligible", "cisa": "eligible", "dod": "none", "locked": false, "csfBox": "ticked", "ztBox": "unticked", "ztFramework": null, "generate": "enabled", "copy": null, "disabledRows": []},
  {"id": "A38", "csf": "eligible", "cisa": "eligible", "dod": "none", "locked": false, "csfBox": "ticked", "ztBox": "ticked", "ztFramework": null, "generate": "enabled", "copy": null, "disabledRows": []},
  {"id": "A39", "csf": "eligible", "cisa": "eligible", "dod": "no_record", "locked": false, "csfBox": "unticked", "ztBox": "unticked", "ztFramework": null, "generate": "disabled", "copy": "5a", "disabledRows": ["Zero Trust (DoD ZT Reference Architecture)"]},
  {"id": "A40", "csf": "eligible", "cisa": "eligible", "dod": "no_record", "locked": false, "csfBox": "unticked", "ztBox": "ticked", "ztFramework": null, "generate": "enabled", "copy": null, "disabledRows": ["Zero Trust (DoD ZT Reference Architecture)"]},
  {"id": "A41", "csf": "eligible", "cisa": "eligible", "dod": "no_record", "locked": false, "csfBox": "ticked", "ztBox": "unticked", "ztFramework": null, "generate": "enabled", "copy": null, "disabledRows": ["Zero Trust (DoD ZT Reference Architecture)"]},
  {"id": "A42", "csf": "eligible", "cisa": "eligible", "dod": "no_record", "locked": false, "csfBox": "ticked", "ztBox": "ticked", "ztFramework": null, "generate": "enabled", "copy": null, "disabledRows": ["Zero Trust (DoD ZT Reference Architecture)"]},
  {"id": "A43", "csf": "eligible", "cisa": "eligible", "dod": "eligible", "locked": false, "csfBox": "unticked", "ztBox": "unticked", "ztFramework": null, "generate": "disabled", "copy": "5a", "disabledRows": []},
  {"id": "A44", "csf": "eligible", "cisa": "eligible", "dod": "eligible", "locked": false, "csfBox": "unticked", "ztBox": "ticked", "ztFramework": null, "generate": "disabled", "copy": "17", "disabledRows": []},
  {"id": "A45", "csf": "eligible", "cisa": "eligible", "dod": "eligible", "locked": false, "csfBox": "unticked", "ztBox": "ticked", "ztFramework": "cisa_ztmm_2_0", "generate": "enabled", "copy": null, "disabledRows": []},
  {"id": "A46", "csf": "eligible", "cisa": "eligible", "dod": "eligible", "locked": false, "csfBox": "unticked", "ztBox": "ticked", "ztFramework": "dod_ztra", "generate": "enabled", "copy": null, "disabledRows": []},
  {"id": "A47", "csf": "eligible", "cisa": "eligible", "dod": "eligible", "locked": false, "csfBox": "ticked", "ztBox": "unticked", "ztFramework": null, "generate": "enabled", "copy": null, "disabledRows": []},
  {"id": "A48", "csf": "eligible", "cisa": "eligible", "dod": "eligible", "locked": false, "csfBox": "ticked", "ztBox": "ticked", "ztFramework": null, "generate": "disabled", "copy": "17", "disabledRows": []},
  {"id": "A49", "csf": "eligible", "cisa": "eligible", "dod": "eligible", "locked": false, "csfBox": "ticked", "ztBox": "ticked", "ztFramework": "cisa_ztmm_2_0", "generate": "enabled", "copy": null, "disabledRows": []},
  {"id": "A50", "csf": "eligible", "cisa": "eligible", "dod": "eligible", "locked": false, "csfBox": "ticked", "ztBox": "ticked", "ztFramework": "dod_ztra", "generate": "enabled", "copy": null, "disabledRows": []},
];

const COPY_5A =
  "Choose NIST CSF, Zero Trust, or both. ATT&CK coverage alone is not enough for a register.";
const COPY_17 = "Choose a Zero Trust framework.";
const copy18 = (label: string): string =>
  `${label}: no assessment yet, so it cannot be included.`;

const ATTACK: RiskSelectableService = {
  kind: "attack",
  service_id: "svc-attack",
  title: "ATT&CK",
  framework: null,
  label: "ATT&CK coverage",
};
const SERVICES: Record<"csf" | "cisa" | "dod", RiskSelectableService> = {
  csf: {
    kind: "csf",
    service_id: "svc-csf",
    title: "CSF",
    framework: null,
    label: "NIST CSF",
  },
  cisa: {
    kind: "zt",
    service_id: "svc-cisa",
    title: "ZT CISA",
    framework: "cisa_ztmm_2_0",
    label: "Zero Trust (CISA ZTMM 2.0)",
  },
  dod: {
    kind: "zt",
    service_id: "svc-dod",
    title: "ZT DoD",
    framework: "dod_ztra",
    label: "Zero Trust (DoD ZT Reference Architecture)",
  },
};
const KEYS = ["csf", "cisa", "dod"] as const;

function gateFor(row: Row): RiskGate {
  const eligible = KEYS.filter((k) => row[k] === "eligible").map(
    (k) => SERVICES[k],
  );
  const ineligible = KEYS.filter((k) => row[k] === "no_record").map(
    (k) => SERVICES[k],
  );
  const hasCsf = row.csf === "eligible";
  const hasZt = row.cisa === "eligible" || row.dod === "eligible";
  return {
    unlocked: hasCsf || hasZt,
    has_attack: true,
    has_csf: hasCsf,
    has_zt: hasZt,
    eligible: [ATTACK, ...eligible],
    ineligible,
    missing: [],
    not_finalized: [],
    synthesizable_missing: [],
    attack_catalog_mismatch: null,
    inputs: [],
    locked_inputs: [],
  };
}

function mockPickedClient(): void {
  vi.mocked(clientReads.readClientList).mockResolvedValue({
    clients: [
      {
        id: "c1",
        legal_name: "Atlas",
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
  vi.mocked(clientReads.readActiveClient).mockResolvedValue({ active: "c1" });
}

async function loaded(): Promise<void> {
  render(<RiskRegisterDashboard />);
  await waitFor(() => {
    expect(
      screen.getByRole("heading", { name: /^Risk Register for / }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Loading…")).toBeNull();
  });
}

/** The ZT checkbox's label: the framework's own with one, "Zero Trust" with two. */
function ztLabel(row: Row): string {
  const zt = (["cisa", "dod"] as const).filter((k) => row[k] === "eligible");
  return zt.length === 1 ? SERVICES[zt[0]].label : "Zero Trust";
}

function expectedInclude(row: Row): unknown {
  const csf =
    row.csf === "eligible" &&
    (row.csfBox === "ticked" || row.csfBox === "ticked (required)");
  const zt = (["cisa", "dod"] as const).filter((k) => row[k] === "eligible");
  const ztOn = row.ztBox === "ticked" || row.ztBox === "ticked (required)";
  let zero_trust: string | null = null;
  if (ztOn) {
    zero_trust =
      zt.length === 1 ? SERVICES[zt[0]].framework : (row.ztFramework ?? null);
  }
  return { csf, zero_trust };
}

describe("Matrix A, page (design note rev 12 §2a)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPickedClient();
    vi.mocked(riskClient.fetchRiskRegisterLatest).mockResolvedValue(null);
    vi.mocked(riskClient.generateRiskRegister).mockReturnValue(
      new Promise(() => {}),
    );
  });

  it("covers every row of the table", () => {
    // A row lost from the extraction would pass by its absence.
    expect(MATRIX_A_PAGE.map((r) => r.id)).toEqual(
      Array.from({ length: 50 }, (_, i) => `A${i + 1}`),
    );
  });

  it.each(MATRIX_A_PAGE.map((r) => [r.id, r] as const))(
    "%s",
    async (_id, row) => {
      vi.mocked(riskClient.fetchRiskGate).mockResolvedValue(gateFor(row));
      await loaded();

      if (row.locked) {
        expect(screen.queryByTestId("risk-selection-block")).toBeNull();
        expect(screen.queryByRole("button", { name: "Generate" })).toBeNull();
        return;
      }

      const block = await screen.findByTestId("risk-selection-block");
      const attack = within(block).getByRole("checkbox", {
        name: "ATT&CK coverage, required",
      });
      expect(attack).toBeChecked();
      expect(attack).toBeDisabled();

      // CSF box.
      if (row.csfBox === "n/a") {
        expect(
          within(block).queryByRole("checkbox", { name: /NIST CSF/ }),
        ).toBeNull();
      } else if (row.csfBox === "ticked (required)") {
        const box = within(block).getByRole("checkbox", {
          name: "NIST CSF, required",
        });
        expect(box).toBeChecked();
        expect(box).toBeDisabled();
      } else {
        const box = within(block).getByRole("checkbox", { name: "NIST CSF" });
        expect(box).toBeEnabled();
        if (row.csfBox === "unticked") fireEvent.click(box);
        expect((box as HTMLInputElement).checked).toBe(row.csfBox === "ticked");
      }

      // ZT box and radio.
      const label = ztLabel(row);
      if (row.ztBox === "n/a") {
        expect(
          within(block).queryByRole("checkbox", { name: /Zero Trust/ }),
        ).toBeNull();
      } else if (row.ztBox === "ticked (required)") {
        const box = within(block).getByRole("checkbox", {
          name: `${label}, required`,
        });
        expect(box).toBeChecked();
        expect(box).toBeDisabled();
      } else {
        const box = within(block).getByRole("checkbox", { name: label });
        expect(box).toBeEnabled();
        if (row.ztBox === "unticked") fireEvent.click(box);
        expect((box as HTMLInputElement).checked).toBe(row.ztBox === "ticked");
      }
      const twoFrameworks = row.cisa === "eligible" && row.dod === "eligible";
      if (twoFrameworks) {
        const cisa = within(block).getByRole("radio", {
          name: "CISA ZTMM 2.0",
        });
        const dod = within(block).getByRole("radio", {
          name: "DoD ZT Reference Architecture",
        });
        // Fail closed (Q2): neither framework is preselected.
        expect(cisa).not.toBeChecked();
        expect(dod).not.toBeChecked();
        if (row.ztFramework === "cisa_ztmm_2_0") fireEvent.click(cisa);
        if (row.ztFramework === "dod_ztra") fireEvent.click(dod);
      } else {
        expect(within(block).queryByRole("radio")).toBeNull();
      }

      // Copy 18, one line per engaged service with no assessment.
      expect(
        within(block)
          .queryAllByTestId("risk-selection-ineligible")
          .map((el) => el.textContent),
      ).toEqual((row.disabledRows ?? []).map(copy18));

      // Copy 5a and 17: exactly the one the row names, or neither.
      const needs = within(block).queryByTestId(
        "risk-selection-needs-csf-or-zt",
      );
      const hint = within(block).queryByTestId("risk-selection-zt-hint");
      if (row.copy === "5a") expect(needs).toHaveTextContent(COPY_5A);
      else expect(needs).toBeNull();
      if (row.copy === "17") expect(hint).toHaveTextContent(COPY_17);
      else expect(hint).toBeNull();

      const generate = screen.getByRole("button", { name: "Generate" });
      if (row.generate === "disabled") {
        expect(generate).toBeDisabled();
        return;
      }
      expect(generate).toBeEnabled();
      await act(async () => {
        fireEvent.click(generate);
      });
      expect(riskClient.generateRiskRegister).toHaveBeenCalledWith(
        "c1",
        expectedInclude(row),
      );
    },
  );
});
