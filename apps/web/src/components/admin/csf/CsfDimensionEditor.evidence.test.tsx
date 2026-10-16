import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as csfClient from "@/lib/csf/client";
import type { CsfDimensionScore } from "@/lib/csf/types";

import { CsfDimensionEditor } from "./CsfDimensionEditor";

/**
 * CSF Options 1 and 3 in the dimension editor, in the text Gene approved
 * (#736 6205956728): the level line reads the level's name and says what the
 * evidence value means (C6), a Managed or Optimized level with neither is
 * notional (E2), and the evidence control is a three-value choice (E1). Every
 * expected string is typed here, never imported. Harness from
 * CsfDimensionEditor.help.test.tsx.
 */
vi.mock("@/lib/csf/client", () => ({
  CsfProxyError: class CsfProxyError extends Error {},
  fetchProfile: vi.fn(),
  patchDimensionScore: vi.fn(),
}));

function row(overrides: Partial<CsfDimensionScore> = {}): CsfDimensionScore {
  // All five dimensions 2: total 10, level 5 (Optimized), uncapped.
  return {
    id: "row-1",
    tier: "high",
    subcategory_code: "GV.OC-01",
    governance: 2,
    policy: 2,
    implementation: 2,
    monitoring: 2,
    improvement: 2,
    in_scope: true,
    rationale: null,
    what_we_found: null,
    evidence_status: "neither",
    has_evidence: false,
    target_level: 3,
    locked: false,
    total: 10,
    level: 5,
    evidence_capped: false,
    ...overrides,
  };
}

async function renderWith(r: CsfDimensionScore) {
  vi.mocked(csfClient.fetchProfile).mockResolvedValue({
    tier: "high",
    rows: [r],
  });
  render(<CsfDimensionEditor serviceId="svc-1" />);
  // Positive state first: the row has loaded.
  await screen.findByRole("radiogroup", { name: "Governance" });
}

const NEITHER_NOTE = "(not validated by evidence)";
const CONFIRMED_NOTE = "(confirmed in discussion; no evidence on file)";
const OPTIMIZED_NOTIONAL =
  "Optimized is notional: no evidence is on file and it was not confirmed in discussion.";

beforeEach(() => {
  vi.mocked(csfClient.fetchProfile).mockReset();
});

describe("CsfDimensionEditor, evidence labels the level (Options 1 and 3)", () => {
  it("names the level and says it is not validated, and notional, with neither", async () => {
    await renderWith(row());
    expect(screen.getByTestId("csf-level-name")).toHaveTextContent("Optimized");
    expect(screen.getByTestId("csf-level-evidence")).toHaveTextContent(
      NEITHER_NOTE,
    );
    expect(screen.getByTestId("csf-level-notional")).toHaveTextContent(
      OPTIMIZED_NOTIONAL,
    );
  });

  it("says confirmed in discussion, and is not notional, when it was", async () => {
    await renderWith(row({ evidence_status: "confirmed_in_discussion" }));
    expect(screen.getByTestId("csf-level-evidence")).toHaveTextContent(
      CONFIRMED_NOTE,
    );
    expect(screen.queryByTestId("csf-level-notional")).toBeNull();
  });

  it("adds nothing with evidence on file", async () => {
    await renderWith(row({ evidence_status: "on_file", has_evidence: true }));
    expect(screen.getByTestId("csf-level-name")).toHaveTextContent("Optimized");
    expect(screen.queryByTestId("csf-level-evidence")).toBeNull();
    expect(screen.queryByTestId("csf-level-notional")).toBeNull();
  });

  it("is not notional below Managed, with neither", async () => {
    // G2 P2 I2 M1 C0: total 7, level 3 (Defined).
    await renderWith(
      row({ monitoring: 1, improvement: 0, total: 7, level: 3 }),
    );
    expect(screen.getByTestId("csf-level-name")).toHaveTextContent("Defined");
    expect(screen.getByTestId("csf-level-evidence")).toHaveTextContent(
      NEITHER_NOTE,
    );
    expect(screen.queryByTestId("csf-level-notional")).toBeNull();
  });

  it("offers the three evidence values, showing the row's", async () => {
    await renderWith(row({ evidence_status: "confirmed_in_discussion" }));
    const select = screen.getByRole("combobox", {
      name: "Evidence",
    });
    expect(select).toHaveValue("confirmed_in_discussion");
    expect(
      Array.from(select.querySelectorAll("option")).map((o) => o.textContent),
    ).toEqual(["Evidence on file", "Confirmed in discussion", "Neither"]);
  });

  it("reads an older API's has_evidence as the value 0074 mapped it to", async () => {
    const older = row({ has_evidence: true });
    delete older.evidence_status;
    await renderWith(older);
    expect(screen.getByRole("combobox", { name: "Evidence" })).toHaveValue(
      "on_file",
    );
  });
});
