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
    entries_total: 0,
    entries_without_tier: 0,
    entries_with_dropped_links: 0,
    entries_unlinked_after_drops: 0,
    entries_links_not_recorded: 0,
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
describe("RiskRegisterDashboard tier-less entries disclosure", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getActiveClientId.mockResolvedValue("c1");
    getClientName.mockResolvedValue("Atlas");
    fetchRiskGate.mockResolvedValue(gate());
  });

  it("says so when entries reached the register with no tier", async () => {
    // #121. Such an entry renders as em dashes, is dropped from the 5x5
    // matrix, and is STILL counted by "Entries" -- so that card can read 40
    // while the matrix sums to fewer, with nothing explaining the gap.
    //
    // Derived server-side from the stored entries, so unlike the
    // excluded-inputs banner this arrives on a plain LOAD, not only after a
    // Generate. That is what this test asserts by mocking `latest`.
    fetchRiskRegisterLatest.mockResolvedValue(
      register({ entries_total: 40, entries_without_tier: 12 }),
    );
    await loaded();

    const alert = await screen.findByTestId("risk-entries-without-tier");
    expect(alert.textContent).toMatch(/12 of 40/);
    expect(alert).toHaveAttribute("role", "alert");
    // Names the remedy, not just the count.
    expect(alert.textContent).toMatch(/Regenerate before exporting/i);
  });

  it("stays quiet when every entry has a tier", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(
      register({ entries_total: 40, entries_without_tier: 0 }),
    );
    await loaded();
    expect(screen.queryByTestId("risk-entries-without-tier")).toBeNull();
  });

  it("says so when entries proposed links and kept none", async () => {
    // #132. Such an entry is persisted with empty link arrays -- identical to
    // an entry nobody linked -- so the consultant reads "the AI found no
    // relevance" over "the AI proposed five things and all five were
    // misspelled". Derived server-side and persisted (migration 0048), so it
    // arrives on a plain LOAD rather than only on the generate response, which
    // is what mocking `latest` asserts.
    fetchRiskRegisterLatest.mockResolvedValue(
      register({
        entries_total: 40,
        entries_with_dropped_links: 9,
        entries_unlinked_after_drops: 3,
      }),
    );
    await loaded();

    const alert = await screen.findByTestId(
      "risk-entries-unlinked-after-drops",
    );
    expect(alert.textContent).toMatch(/3 of 40/);
    expect(alert).toHaveAttribute("role", "alert");
    expect(alert.textContent).toMatch(/Regenerate before exporting/i);
    // The OUTCOME count, not the spelling-problem count. Nine entries have a
    // dropped value and six of them still show linkage; saying 9 would send
    // the consultant looking for six absences that are not there.
    expect(alert.textContent).not.toMatch(/9 of 40/);
  });

  it("stays quiet when dropped links still left something to show", async () => {
    // The discriminator between the two counters. Entries lost a value and
    // kept linkage, so nothing on screen is missing and the banner must not
    // fire -- a banner keyed on `entries_with_dropped_links` would.
    fetchRiskRegisterLatest.mockResolvedValue(
      register({
        entries_total: 40,
        entries_with_dropped_links: 9,
        entries_unlinked_after_drops: 0,
      }),
    );
    await loaded();
    expect(
      screen.queryByTestId("risk-entries-unlinked-after-drops"),
    ).toBeNull();
  });
});

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
