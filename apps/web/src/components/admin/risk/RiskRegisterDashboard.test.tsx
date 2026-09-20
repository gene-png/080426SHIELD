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
    // #372. `null` is the honest default: most registers in these fixtures are
    // not the product of a recorded generate run, and `null` is exactly what
    // the server sends for those. Defaulting to `0` would have every fixture
    // assert "nothing failed", which is a claim, not an absence.
    batches_total: null,
    batches_failed: null,
    // #330, and `null` for the same reason as the pair above: the server
    // declares `int | None = None` and sends the KEY carrying null, so a
    // fixture omitting it would build a response shape the API never emits.
    entries_intended: null,
    excluded_inputs: [],
    // #244. `true` here means "the server looked and there was nothing", which
    // is what every register generated today reports. The `false` case -- a
    // pre-0047 register whose exclusions were never recorded -- is a separate
    // banner and is set explicitly in the test for it, because defaulting it
    // here would make every other test silently exercise the wrong state.
    excluded_inputs_recorded: true,
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
 * **That was true when written and is now false, and the correction matters
 * more than the original.** This block used to say `generateRiskRegister` was
 * the ONLY producer of a non-empty withheld set, because `fetchRiskRegisterLatest`
 * "always returns `[]`". #316 persisted the set and taught `latest` and
 * `export` to read it back, so all three carry it now.
 *
 * Left standing, that sentence told the next reader that a `latest`-driven
 * fixture describes a response the API cannot emit — so the right move would
 * have looked like DELETING the `fetchRiskRegisterLatest` tests below as
 * invalid, and writing no `latest` test for this field. That belief is exactly
 * what let #244 live for a release.
 *
 * The original defect it records is real and still worth knowing: the first
 * version of these tests drove the one path that could not carry the field, so
 * the export defect was invisible to a green suite.
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
    // Derived server-side from the stored entries, so it arrives on a plain
    // LOAD. That is what this test asserts by mocking `latest`.
    //
    // The contrast this used to draw -- "unlike the excluded-inputs banner",
    // which arrived only after a Generate -- is dead as of #316: the withheld
    // set is persisted and `latest` returns it. A contrast-by-comparison is
    // how the claim survived one sweep already; it asserts something about
    // ANOTHER field without naming it in a way a grep for that field finds.
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

  it("says an OLD register was never asked, rather than reporting it clean", async () => {
    // #244. `excluded_inputs: []` carries two facts and only one flag tells
    // them apart: "the server looked and nothing was excluded", and "this
    // register predates provenance recording, so nobody looked". Rendering the
    // second as the first is a false assurance about the one population that
    // cannot be re-checked -- `CLAUDE.md`'s standing rule that missing data
    // defaults to UNCONFIRMED.
    //
    // Both branches asserted: the not-recorded banner appears, and the
    // excluded-inputs banner does NOT, because proving one renders says
    // nothing about whether the other wrongly renders beside it.
    fetchRiskRegisterLatest.mockResolvedValue(
      register({ excluded_inputs: [], excluded_inputs_recorded: false }),
    );
    await loaded();
    const banner = await screen.findByTestId(
      "risk-register-exclusions-not-recorded",
    );
    expect(banner.textContent).toMatch(/before SHIELD recorded/i);
    expect(banner.textContent).toMatch(/not the same as none having been/i);
    expect(screen.queryByTestId(BANNER)).not.toBeInTheDocument();
  });

  it("says nothing about exclusions when no register exists at all", async () => {
    // The guard on `register != null`. A client with nothing generated has no
    // record to have a gap in, and announcing one would be a warning about a
    // document that does not exist.
    fetchRiskRegisterLatest.mockResolvedValue(null);
    await loaded();
    expect(
      screen.queryByTestId("risk-register-exclusions-not-recorded"),
    ).not.toBeInTheDocument();
  });

  it("KEEPS the disclosure after Export — the action it warns about", async () => {
    // The regression this file exists for, and the GUARANTEE HAS MOVED (#244).
    //
    // `export` used to return the register WITHOUT `excluded_inputs`, the
    // schema defaulted it to `[]`, and assigning component state from that
    // response erased the banner at exactly the moment the deliverable was
    // produced. The fix was to hold the withheld set in separate state that no
    // later response could clear.
    //
    // `_serialize` now reads the set back from the persisted snapshot on every
    // path, so the export response carries it and the component derives the
    // banner from whatever register is in hand. The mock is updated to match:
    // `excluded_inputs: []` on export is a state THE SERVER NO LONGER
    // PRODUCES, and a fixture asserting against an impossible response pins
    // nothing about the product.
    //
    // The test is kept because the property is the same one -- the disclosure
    // survives the action it warns about.
    //
    // It does NOT cover `_serialize`. An earlier version of this comment said
    // it "fails if `_serialize` stops reading the snapshot back", which it
    // structurally cannot: `exportRiskRegister` is mocked and hands the
    // component a register directly, so the Python never runs. Nor does it
    // discriminate the derivation -- revert the component to the separate-state
    // version and this still passes, because generate sets the state and export
    // never clears it.
    //
    // What covers `_serialize` is `test_the_withheld_set_survives_a_reload` in
    // `apps/api/tests/unit/test_risk_register.py`, which goes red when the
    // read-back branch is deleted. Stated here because a comment claiming a
    // guarantee is where someone checks for one.
    generateRiskRegister.mockResolvedValue(
      register({ excluded_inputs: ["the Zero Trust assessment"] }),
    );
    exportRiskRegister.mockResolvedValue(
      register({
        excluded_inputs: ["the Zero Trust assessment"],
        finalized_at: "2026-09-09T01:00:00Z",
      }),
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
    // There is no #240 limitation left to pin: `latest` returns the persisted
    // set. This comment used to say it did not, and claimed this test pinned
    // that limitation — so a reader trying to remove the limitation expected
    // this test to stand in their way, and it would not have.
    //
    // What it actually covers: a register whose `excluded_inputs` is empty
    // renders no banner. The "nothing generated yet" case is the
    // `mockResolvedValue(null)` test above; this one mocks a register, so the
    // name below overstates it.
    fetchRiskRegisterLatest.mockResolvedValue(
      register({ excluded_inputs: [] }),
    );
    await loaded();
    expect(screen.queryByTestId(BANNER)).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// #372 -- a partial synthesis KEEPS what succeeded, so the register renders
// SHORT. The endpoint has always returned `batches_total` / `batches_failed`;
// `lib/risk/types.ts` did not declare them, so they were dropped at the
// TypeScript boundary and nothing could render them. ATT&CK fixed the
// identical pair as #115.
//
// EXERCISED THROUGH GENERATE **AND** THROUGH `latest`, and the second half is
// new. This block used to say a `latest` fixture carrying `batches_failed: 3`
// "would build a state the API cannot produce" -- correct then, because the
// counts were response-only and a read-back defaulted to 0.
//
// That default was the defect. It made `export` erase the INCOMPLETE warning
// at the exact moment the consultant produced the deliverable, and a reload do
// the same. The tally is persisted now, so a `latest` carrying a real failure
// count is a state the writer EMITS, and a test that mocks it is testing the
// product rather than an impossible fixture.
//
// The unreachable-state rule has not been relaxed -- the reachable set moved,
// and this comment is what tells the next reader which.
// ---------------------------------------------------------------------------

describe("RiskRegisterDashboard partial-synthesis disclosure (#372)", () => {
  beforeEach(() => {
    getActiveClientId.mockResolvedValue("c1");
    getClientName.mockResolvedValue("Atlas");
    fetchRiskGate.mockResolvedValue(gate());
    fetchRiskRegisterLatest.mockResolvedValue(null);
  });

  async function generated(over: Partial<RiskRegister>): Promise<void> {
    generateRiskRegister.mockResolvedValue(register(over));
    await loaded();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Generate" }));
    });
  }

  it("says the register is incomplete when a batch failed", async () => {
    await generated({ batches_total: 12, batches_failed: 3 });

    const note = await screen.findByTestId("risk-batches-failed");
    // BOTH operands. "3 batches failed" does not tell a consultant whether
    // that is three of four or three of forty, and the decision -- regenerate
    // or ship -- turns on exactly that.
    expect(note.textContent).toMatch(/3 of 12/);
    // The word that makes it actionable rather than ambient, and the remedy.
    expect(note.textContent).toMatch(/INCOMPLETE/);
    expect(note.textContent).toMatch(/Regenerate before exporting/i);
    expect(note).toHaveAttribute("role", "alert");
  });

  it("KEEPS the disclosure after Export — the action it warns about", async () => {
    // THE DEFECT THIS BLOCK WAS MISSING, and the sibling block one screen up
    // pins the identical property for `excluded_inputs` because it was burned
    // by it first.
    //
    // `onExport` does `setRegister(await exportRiskRegister(cid))`. While the
    // tally was response-only, `export` built its response from a STORED
    // register, so it carried the schema default and this line erased the
    // "INCOMPLETE" warning at the exact moment the consultant produced the
    // deliverable it was warning about. Generate, see INCOMPLETE, click
    // Export, banner gone, short register in the client's XLSX.
    //
    // It is persisted now, so the export response carries it. The mock says
    // so: a `0/0` export response is a state the server no longer produces.
    await generated({ batches_total: 12, batches_failed: 3 });
    await screen.findByTestId("risk-batches-failed");

    exportRiskRegister.mockResolvedValue(
      register({
        batches_total: 12,
        batches_failed: 3,
        finalized_at: "2026-09-21T01:00:00Z",
      }),
    );
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "Export XLSX / PDF / Word" }),
      );
    });
    await waitFor(() => expect(exportRiskRegister).toHaveBeenCalled());

    expect(screen.getByTestId("risk-batches-failed").textContent).toMatch(
      /3 of 12/,
    );
  });

  it("KEEPS the disclosure on a reload, because the tally is persisted", async () => {
    // The other half, and what the previous revision got wrong. It shipped a
    // banner whose own copy promised it would vanish, and a comment calling
    // that "the same limitation the withheld-inputs banner below carries" --
    // which was false, that one is persisted and survives.
    //
    // This is a `latest` read with no generate in front of it: the component
    // has no run-scoped memory to fall back on, so a pass here can only come
    // from `_serialize` having read the tally back out of provenance.
    fetchRiskRegisterLatest.mockResolvedValue(
      register({ batches_total: 12, batches_failed: 3 }),
    );
    await loaded();

    const note = await screen.findByTestId("risk-batches-failed");
    expect(note.textContent).toMatch(/3 of 12/);
    // And it must not promise its own disappearance any more.
    expect(note.textContent).not.toMatch(/will not reappear/i);
  });

  it("stays silent when every batch succeeded", async () => {
    await generated({ batches_total: 12, batches_failed: 0 });
    expect(screen.queryByTestId("risk-batches-failed")).toBeNull();
  });

  it("stays silent when NOBODY COUNTED, rather than reporting complete", async () => {
    // `null` is a register generated before the tally was persisted. It is not
    // "nothing failed" and it is not "something failed" -- nobody looked.
    //
    // Renders nothing, deliberately, and this is the one place the PR does NOT
    // fail closed: there is no record to fail closed on, and a permanent
    // "completeness unrecorded" banner on every historical register is
    // furniture that teaches readers to skip the real one. What it does
    // instead is refuse to assert the positive -- the register is never
    // described as complete anywhere.
    //
    // Asserted so nobody "improves" `!== null` into `?? 0`, which would make a
    // never-counted register indistinguishable from a clean one.
    fetchRiskRegisterLatest.mockResolvedValue(
      register({ batches_total: null, batches_failed: null }),
    );
    await loaded();
    expect(screen.queryByTestId("risk-batches-failed")).toBeNull();
  });
});

// #330 -- the banner divided by the wrong quantity.
//
// `entries_total` named two things: the generate loop's INTENDED tally (audit
// row) and the table READ-BACK (response). They agree on every run any current
// writer can produce, and diverge in exactly one state -- a row lost between
// `db.add` and the flush.
//
// The banner rendered `{entries_without_tier} of {entries_total}` against the
// POST-LOSS denominator, so a register that lost a row presented as complete:
// "0 of 1" rather than "0 of 2", with the missing row invisible. That is
// CLAUDE.md's withheld-denominator shape reached from a different direction --
// the withholding is not deliberate, it is two variables sharing a name.
//
// Latent: no current writer produces the divergent state. Pinned anyway,
// because the names will outlive the measurements that make them safe, and
// the failure is silent AND optimistic when it fires.
// ---------------------------------------------------------------------------

describe("RiskRegisterDashboard denominator (#330)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getActiveClientId.mockResolvedValue("c1");
    getClientName.mockResolvedValue("Atlas");
    fetchRiskGate.mockResolvedValue(gate());
  });

  it("divides by the INTENDED count, not the post-loss one", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(
      register({
        entries_total: 1,
        entries_intended: 2,
        entries_without_tier: 0,
      }),
    );
    await loaded();

    const note = screen.getByTestId("risk-entries-lost");
    // THE EXACT PHRASE, not the digits separately. A first draft asserted
    // `/2/` and `/1/` and passed with the denominator swapped to the
    // post-loss count -- because the banner mentions BOTH numbers again
    // later ("over 1 rows and not 2"), so the loose match was satisfied
    // elsewhere in the same element. Measured, by making that swap and
    // watching the test stay green.
    expect(note).toHaveTextContent("1 of 2 entries did not reach storage");
  });

  it("stays silent when the two agree", async () => {
    fetchRiskRegisterLatest.mockResolvedValue(
      register({
        entries_total: 2,
        entries_intended: 2,
        entries_without_tier: 0,
      }),
    );
    await loaded();
    expect(screen.queryByTestId("risk-entries-lost")).not.toBeInTheDocument();
  });

  it("stays silent when the intended count was never recorded", async () => {
    // A register generated before #330 carries a NULL `entries_intended` --
    // the key arrives, the value is null. That is "nobody counted", not
    // "nothing was lost", and it must not render a loss banner built from an
    // absent operand.
    //
    // Written explicitly rather than left to the factory default, because the
    // whole point of this case is WHICH absence it tests: null-on-the-wire,
    // which the server emits, and not an omitted key, which it never does.
    fetchRiskRegisterLatest.mockResolvedValue(
      register({
        entries_total: 2,
        entries_without_tier: 0,
        entries_intended: null,
      }),
    );
    await loaded();
    expect(screen.queryByTestId("risk-entries-lost")).not.toBeInTheDocument();
  });
});
