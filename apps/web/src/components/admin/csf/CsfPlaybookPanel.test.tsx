import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as csfClient from "@/lib/csf/client";
import type { CsfRunAiResponse, EnterpriseProfile } from "@/lib/csf/types";

import { CsfPlaybookPanel } from "./CsfPlaybookPanel";

// Deterministic + offline: the lib client is mocked, and the child editors /
// preview button are stubbed so this test isolates CsfPlaybookPanel's own
// enterprise-profile fetch and its reqSeq stale-fetch guard.
vi.mock("@/lib/csf/client", () => ({
  CsfProxyError: class CsfProxyError extends Error {},
  fetchEnterpriseProfile: vi.fn(),
  seedProfiles: vi.fn(),
  runCsfAi: vi.fn(),
  exportPlaybook: vi.fn(),
}));
vi.mock("../AiPreviewButton", () => ({ AiPreviewButton: () => null }));
vi.mock("./CsfDimensionEditor", () => ({ CsfDimensionEditor: () => null }));
vi.mock("./CsfGapActionEditor", () => ({ CsfGapActionEditor: () => null }));
// The guard owns its own AI-status fetch and is pinned by RunAiGuard.test.tsx.
// Passing the click straight through keeps these tests about the accounting.
vi.mock("../RunAiGuard", () => ({
  RunAiGuard: ({
    onProceed,
    children,
  }: {
    onProceed: () => void;
    children: (props: { onClick: () => void }) => React.ReactNode;
  }) => children({ onClick: onProceed }),
}));

const fetchEnterpriseProfile = vi.mocked(csfClient.fetchEnterpriseProfile);
const seedProfiles = vi.mocked(csfClient.seedProfiles);
const runCsfAi = vi.mocked(csfClient.runCsfAi);

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (err: unknown) => void;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (err: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function ent(code: string): EnterpriseProfile {
  return {
    tiers_in_use: ["moderate"],
    subcategories: [
      {
        subcategory_code: code,
        name: `${code} outcome`,
        function: "GV",
        tier_levels: { moderate: 2 },
        enterprise_level: 2,
        rollup_rule: 1,
        target_level: 3,
        gap: false,
        priority: null,
      },
    ],
  };
}

describe("CsfPlaybookPanel reqSeq stale-fetch guard", () => {
  it("discards a stale mount fetch that resolves after a newer reload", async () => {
    const first = deferred<EnterpriseProfile>(); // mount fetch (seq 1) — slow
    const second = deferred<EnterpriseProfile>(); // post-seed reload (seq 2)
    fetchEnterpriseProfile
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    seedProfiles.mockResolvedValue(["moderate"]);

    render(<CsfPlaybookPanel serviceId="svc-1" />);

    // Mount fetch is in-flight (enterprise still null => not seeded), so the
    // Seed button is offered. Clicking it triggers the second fetch (seq 2).
    fireEvent.click(
      await screen.findByRole("button", { name: "Seed Working Profiles" }),
    );
    await act(async () => {
      // seedProfiles resolves, then reload() issues the seq-2 fetch.
      await Promise.resolve();
    });
    expect(fetchEnterpriseProfile).toHaveBeenCalledTimes(2);

    // Newer request (seq 2) resolves first with the fresh data.
    await act(async () => {
      second.resolve(ent("FRESH.1"));
    });

    // The slow mount fetch (seq 1) resolves LATE with stale data. The guard must
    // discard it; without the guard it would overwrite the fresh enterprise.
    await act(async () => {
      first.resolve(ent("STALE.1"));
    });

    expect(await screen.findByText("FRESH.1 outcome")).toBeInTheDocument();
    expect(screen.queryByText("STALE.1 outcome")).not.toBeInTheDocument();
  });

  it("surfaces a failed initial load to the error state (fail loudly)", async () => {
    fetchEnterpriseProfile.mockRejectedValue(new Error("boom-profile"));

    render(<CsfPlaybookPanel serviceId="svc-err" />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("boom-profile");
  });
});

describe("CsfPlaybookPanel run-AI accounting (W1, issue #44)", () => {
  function result(over: Partial<CsfRunAiResponse> = {}): CsfRunAiResponse {
    return {
      changed: [],
      rows: [],
      suggestions_received: 0,
      suggestions_applied: 0,
      dropped: [],
      ...over,
    };
  }

  async function runAi(res: CsfRunAiResponse): Promise<void> {
    fetchEnterpriseProfile.mockResolvedValue(ent("GV.OC-01"));
    runCsfAi.mockResolvedValue(res);
    render(<CsfPlaybookPanel serviceId="svc-run" />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Run AI (csf_score)" }),
    );
    await act(async () => {
      await Promise.resolve();
    });
  }

  it("states the accounting on a CLEAN run, so its absence never means zero", async () => {
    // The F9 lesson (PR #39): once a block only appears when something went
    // wrong, its absence starts reading as "nothing was dropped" — which is
    // precisely the claim a silent drop makes. A clean run must say so out loud.
    await runAi(result({ suggestions_received: 12, suggestions_applied: 12 }));

    expect(
      await screen.findByText(/AI applied/, { exact: false }),
    ).toHaveTextContent("AI applied 12 of 12 suggested score values");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("itemizes a rejected suggestion with the key the model wrote", async () => {
    await runAi(
      result({
        suggestions_received: 2,
        suggestions_applied: 1,
        dropped: [
          {
            reason: "unknown_key",
            key: "high|GV.OC-1",
            field: null,
            values: 1,
            value: null,
          },
        ],
      }),
    );

    const alert = await screen.findByRole("alert");
    // The verbatim key is the point: it shows the catalogue holds GV.OC-01.
    expect(alert).toHaveTextContent("high|GV.OC-1");
    // The reason is about the ROW, not the subcategory: the lookup is on
    // tier + code, so an unseeded tier misses on a code that IS in the
    // catalogue. Claiming "not in the catalogue" sent readers hunting a
    // catalogue defect that does not exist.
    //
    // Asserting the RENDERED SENTENCE, not just a substring: the label sits in
    // front of an em-dash list separator, and the previous wording ended
    // mid-clause so the key read as the end of the sentence
    // ("...and the code spelled — high|GV.OC-1").
    expect(alert).toHaveTextContent(
      "no matching row (is that tier seeded, and the code spelled right?) — high|GV.OC-1",
    );
  });

  it("counts VALUES, not records, in the failure headline", async () => {
    // One unreadable entry costs a whole row's worth of suggestions. Reporting
    // it as "1 could not be applied" is the undercount a bare integer produced.
    await runAi(
      result({
        suggestions_received: 6,
        suggestions_applied: 0,
        dropped: [
          {
            reason: "entry_shape",
            key: null,
            field: null,
            values: 6,
            value: "str",
          },
        ],
      }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "6 suggested score values could not be applied",
    );
  });

  it("refuses to call a zero-suggestion run clean", async () => {
    // A response under the wrong top-level key parses fine and yields an empty
    // list, so no error path fires. "AI applied 0 of 0" then reads exactly as
    // calmly as "12 of 12" — the most reassuring possible way to report a
    // wholly-lost response, from the feature built to stop that happening.
    await runAi(result({ suggestions_received: 0, suggestions_applied: 0 }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("returned no suggestions at all");
    expect(screen.queryByText(/AI applied/)).not.toBeInTheDocument();
  });

  it("shows an unrecognized field WITHOUT crying failure", async () => {
    // A model volunteering an extra key per row has lost nothing. Routing those
    // into the red alert prints "318 could not be applied" over a run where
    // everything asked for was applied — a wrong number on a normal run, which
    // is the #31 trap and PR #39's rule at once. Visible, but not red.
    await runAi(
      result({
        suggestions_received: 2,
        suggestions_applied: 1,
        dropped: [
          {
            reason: "unknown_field",
            key: "high|GV.OC-01",
            field: "policy_and_process",
            values: 1,
            value: null,
          },
        ],
      }),
    );

    // The field NAME is the diagnostic — it is what shows prompt/parser drift.
    expect(await screen.findByText(/does not recognize/)).toBeInTheDocument();
    expect(screen.getByText(/policy_and_process/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("reports a wrapper key as the many values it hides", async () => {
    // One record standing for five. A reader counting bullets must not get a
    // different total from the headline.
    await runAi(
      result({
        suggestions_received: 5,
        suggestions_applied: 0,
        dropped: [
          {
            reason: "unknown_field",
            key: "high|GV.OC-01",
            field: "dimensions",
            values: 5,
            value: null,
          },
        ],
      }),
    );

    expect(await screen.findByText(/does not recognize/)).toHaveTextContent(
      "5 values came back",
    );
    // The single bullet must state the five it stands for, or a reader counting
    // bullets gets a different total from the headline.
    expect(screen.getByRole("listitem")).toHaveTextContent(
      "high|GV.OC-01 dimensions (5 values)",
    );
  });

  it("never says '0 suggested values skipped' over a run that lost everything", async () => {
    // A `locked` record accounts for ZERO values when every field on the locked
    // row was ALSO misnamed — those values are counted under the drifted names
    // they arrived with. The panel then asserted nothing was lost at the moment
    // the most was. Found by W1's ZT step (D-047 round 1), which ported this
    // block and hit the zero case there first; the sibling it was mirroring had
    // the same hole. Fixture mode cannot produce it.
    await runAi(
      result({
        suggestions_received: 2,
        suggestions_applied: 0,
        dropped: [
          {
            reason: "unknown_field",
            key: "high|GV.OC-01",
            field: "policy_and_process",
            values: 2,
            value: null,
          },
          {
            reason: "locked",
            key: "high|GV.OC-01",
            field: null,
            values: 0,
            value: null,
          },
        ],
      }),
    );
    // Grouped by reason since #67 — the copy no longer hardcodes "you locked
    // those rows", because `protected` is a by-design skip nobody locked.
    const skipped = screen.getByText(/skipped —/);
    expect(skipped).toHaveTextContent(/Suggestions across 1 row skipped/);
    expect(skipped).not.toHaveTextContent(/0 suggested value/);
  });

  it("shows an unmapped reason code instead of an empty bullet", async () => {
    // `reason` is a union by convention only — the payload is JSON. An unmapped
    // code used to index to undefined and render nothing, leaving a bullet with
    // the count right and no explanation at all.
    await runAi(
      result({
        suggestions_received: 1,
        suggestions_applied: 0,
        dropped: [
          {
            reason:
              "invented_later" as CsfRunAiResponse["dropped"][number]["reason"],
            key: "high|GV.OC-01",
            field: null,
            values: 1,
            value: null,
          },
        ],
      }),
    );

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("invented_later");
  });

  it("renders the AI-provenance notice alongside the accounting (#68)", async () => {
    // Wiring proof, not copy proof: the component has its own test. This fails
    // if the notice is not rendered beside the panel. CSF's prompt carries the
    // client's interview answers, so the provenance vector is identical to ZT's
    // and covering only ZT would be an unstated exemption.
    await runAi(result({ suggestions_received: 2, suggestions_applied: 2 }));
    expect(
      screen.getByText(/informed by client-submitted input/),
    ).toBeInTheDocument();
  });

  it("keeps a protected-score skip apart from a locked one (#67)", async () => {
    // Two by-design skips with different causes. Neither may raise an alert,
    // and neither may borrow the other's explanation — telling a consultant a
    // row is locked when nobody locked it is a false statement about who
    // decided, which is why the copy is grouped by reason rather than one
    // hardcoded sentence.
    await runAi(
      result({
        suggestions_received: 8,
        suggestions_applied: 4,
        dropped: [
          {
            reason: "locked",
            key: "high|GV.OC-01",
            field: null,
            values: 2,
            value: null,
          },
          {
            reason: "protected",
            key: "high|GV.OC-02",
            field: null,
            values: 2,
            value: null,
          },
        ],
      }),
    );
    expect(screen.queryByRole("alert")).toBeNull();
    const items = screen
      .getAllByRole("listitem")
      .map((li) => li.textContent ?? "");
    expect(items.some((t) => /skipped —.*row is locked/.test(t))).toBe(true);
    expect(items.some((t) => /skipped —.*typed by hand/.test(t))).toBe(true);
  });

  it("renders an inherited Object property as an unrecognized reason", async () => {
    // The twin of the ZT test. `DROP_REASON_LABEL["toString"]` resolves to an
    // inherited FUNCTION, which `??` does not catch and React renders as
    // nothing — the empty bullet the guard exists to prevent. The neighbouring
    // test uses "invented_later", which is `undefined` and so passes under the
    // OLD form too: it cannot detect the hardening it sits beside. Round 4
    // fixed exactly this in ZT and then shipped the CSF port with only the
    // defective test.
    await runAi(
      result({
        suggestions_received: 1,
        suggestions_applied: 0,
        dropped: [
          {
            reason: "toString" as CsfRunAiResponse["dropped"][number]["reason"],
            key: "high|GV.OC-01",
            field: null,
            values: 1,
            value: null,
          },
        ],
      }),
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      /unrecognized reason "toString"/,
    );
  });

  it("keeps a locked-row skip out of the failure alert (#31)", async () => {
    // A human locking a row is the system working. Folding it in with the
    // failures builds a warning that fires during normal work and gets trained
    // away — taking the real ones with it.
    await runAi(
      result({
        suggestions_received: 3,
        suggestions_applied: 1,
        dropped: [
          {
            reason: "locked",
            key: "high|GV.OC-01",
            field: null,
            values: 2,
            value: null,
          },
        ],
      }),
    );

    // Assert the NUMBER, not just the sentence. `values: 2` above is
    // deliberately different from the record count, so a revert of
    // `skippedValues` to `skipped.length` — the same undercount the failure
    // headline is pinned against — fails here instead of passing silently.
    expect(await screen.findByText(/skipped —/)).toHaveTextContent(
      "2 suggested values across 1 row skipped",
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("says the unrecognized values are the shortfall, not extra detail", async () => {
    // The copy used to lead with "Harmless if the model is volunteering extra
    // detail". On the drift this feature exists to catch, the grey block's
    // number and the headline's shortfall are the SAME values — three of five
    // dimensions on every row, gone. A consultant reading "954 applied of 1908"
    // beside "954 came back under names we don't recognize — harmless" would
    // reasonably conclude the 954 were additional, and that nothing was lost.
    await runAi(
      result({
        suggestions_received: 2,
        suggestions_applied: 1,
        dropped: [
          {
            reason: "unknown_field",
            key: "high|GV.OC-01",
            field: "policy_and_process",
            values: 1,
            value: null,
          },
        ],
      }),
    );

    const block = await screen.findByText(/does not recognize/);
    expect(block).toHaveTextContent("part of the shortfall in the line above");
    expect(block).toHaveTextContent("not extra");
    // Still not an alarm — a volunteered extra key must not turn a good run red.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("renders all three buckets at once and they reconcile with the headline", async () => {
    // The stated design goal is that a reader adding up the bullets gets the
    // headline. No test rendered failed + unrecognized + skipped together, so
    // the property was only ever checked one bucket at a time.
    await runAi(
      result({
        suggestions_received: 10,
        suggestions_applied: 3,
        dropped: [
          {
            reason: "out_of_range",
            key: "high|GV.OC-01",
            field: "governance",
            values: 1,
            value: "5",
          },
          {
            reason: "unknown_field",
            key: "high|GV.OC-02",
            field: "dimensions",
            values: 4,
            value: null,
          },
          {
            reason: "locked",
            key: "high|GV.OC-03",
            field: null,
            values: 2,
            value: null,
          },
        ],
      }),
    );

    expect(
      await screen.findByText(/AI applied/, { exact: false }),
    ).toHaveTextContent("AI applied 3 of 10 suggested score values");
    // 3 applied + 1 failed + 4 unrecognized + 2 skipped == 10 received.
    expect(screen.getByRole("alert")).toHaveTextContent(
      "1 suggested score value could not be applied",
    );
    expect(screen.getByText(/does not recognize/)).toHaveTextContent(
      "4 values came back",
    );
    expect(screen.getByText(/skipped —/)).toHaveTextContent(
      "2 suggested values across 1 row skipped",
    );
  });

  it("shows what the model actually sent, not just that it was rejected", async () => {
    // The API carries the offending value verbatim for exactly one purpose — a
    // human reading it — and nothing rendered it. "value fell outside 0–2" with
    // no value is unactionable: a model that wrote 5 is a different problem from
    // one that wrote "high", and the panel showed them identically.
    await runAi(
      result({
        suggestions_received: 1,
        suggestions_applied: 0,
        dropped: [
          {
            reason: "out_of_range",
            key: "high|GV.OC-01",
            field: "governance",
            values: 1,
            value: "5",
          },
        ],
      }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "high|GV.OC-01 governance = 5",
    );
  });

  it("caps a systematic drift instead of printing a wall of bullets", async () => {
    // Drift is systematic by nature: one misnamed dimension over a seeded
    // Playbook is 318 records. Uncapped, that rendered ~318 list items or one
    // 5 KB comma-joined line — the diagnostic collapsing exactly when it counts.
    // The TOTAL still comes from `values`, so capping the list cannot change a
    // reported number.
    await runAi(
      result({
        suggestions_received: 25,
        suggestions_applied: 0,
        dropped: Array.from({ length: 25 }, (_, i) => ({
          reason: "unknown_field" as const,
          key: `high|GV.OC-${i}`,
          field: "policy_and_process",
          values: 1,
          value: null,
        })),
      }),
    );

    expect(await screen.findByText(/does not recognize/)).toHaveTextContent(
      "25 values came back",
    );
    // 10 shown + 1 overflow line.
    expect(screen.getAllByRole("listitem")).toHaveLength(11);
    // "records", not a bare "15": every other number on the panel is in values,
    // and one record can stand for several, so a bare count invites a reader to
    // add it to a value total.
    expect(screen.getByText("and 15 more records")).toBeInTheDocument();
  });

  it("names the row fault even when it accounts for no values of its own", async () => {
    // The shape my own round-3 repair re-opened. An entry naming an unseeded
    // tier AND wrapping its scores under one strange key has no recognized
    // fields, so suppressing the zero-value `unknown_key` record left the run
    // reporting a field-name curiosity in the quiet block and never saying the
    // tier does not exist. The values are counted once, under the name they
    // arrived with; the red alert still has to fire and name the row.
    await runAi(
      result({
        suggestions_received: 5,
        suggestions_applied: 0,
        dropped: [
          {
            reason: "unknown_field",
            key: "moderate|GV.OC-01",
            field: "dimensions",
            values: 5,
            value: null,
          },
          {
            reason: "unknown_key",
            key: "moderate|GV.OC-01",
            field: null,
            values: 0,
            value: null,
          },
        ],
      }),
    );

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("no matching row");
    expect(alert).toHaveTextContent("moderate|GV.OC-01");
    // Never "0 suggested score values could not be applied" — a red alert whose
    // own number is zero reads as a contradiction and gets dismissed.
    expect(alert).toHaveTextContent("Some suggestions could not be applied");
    expect(alert).not.toHaveTextContent("0 suggested score value");
    // The five values are still reported exactly once, in the other block.
    expect(screen.getByText(/does not recognize/)).toHaveTextContent(
      "5 values came back",
    );
  });
});
