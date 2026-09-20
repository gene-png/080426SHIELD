import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuditViewer } from "./AuditViewer";
import type { AuditEntryRow, LlmCallRow } from "@/lib/admin/audit";

vi.mock("@/lib/admin/audit", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/admin/audit")>();
  return {
    ...actual,
    fetchAuditEntries: vi.fn(async () => ({
      entries: entryRows,
      next_cursor: null,
    })),
    fetchLlmCalls: vi.fn(async () => ({ calls: rows, next_cursor: null })),
  };
});

function call(overrides: Partial<LlmCallRow>): LlmCallRow {
  return {
    id: "00000000-0000-0000-0000-000000000001",
    service_id: null,
    client_id: null,
    purpose: "csf_score",
    prompt_version: "v1",
    provider: "fixture",
    model: "fixture-model",
    mode: "fixture",
    input_tokens: 10,
    output_tokens: 20,
    duration_ms: 5,
    status: "completed",
    error_message: null,
    redaction_mode: "strict",
    redacted_counts: null,
    requested_by: "00000000-0000-0000-0000-0000000000aa",
    requested_at: "2026-08-26T00:00:00Z",
    completed_at: "2026-08-26T00:00:01Z",
    correlation_id: null,
    ...overrides,
  };
}

let rows: LlmCallRow[] = [];
let entryRows: AuditEntryRow[] = [];

function entry(overrides: Partial<AuditEntryRow>): AuditEntryRow {
  return {
    id: "00000000-0000-0000-0000-0000000000e1",
    at: "2026-09-20T00:00:00Z",
    actor_user_id: "00000000-0000-0000-0000-0000000000aa",
    action: "risk_register.generated",
    target_type: "risk_register",
    target_id: "00000000-0000-0000-0000-0000000000bb",
    details: null,
    correlation_id: null,
    ...overrides,
  };
}

function mockEntries(entries: AuditEntryRow[]): void {
  entryRows = entries;
}

function renderAuditEntries(): void {
  render(<AuditViewer />);
}

async function showAiTab(): Promise<void> {
  render(<AuditViewer />);
  fireEvent.click(screen.getByTestId("audit-tab-ai"));
  await waitFor(() =>
    expect(screen.getByText(/csf_score/)).toBeInTheDocument(),
  );
}

describe("AuditViewer redaction column (#144)", () => {
  beforeEach(() => {
    rows = [];
  });

  it("renders the mode the call actually ran under", async () => {
    rows = [call({ redaction_mode: "strict" })];
    await showAiTab();

    expect(screen.getByText("strict")).toBeInTheDocument();
  });

  it("renders a pre-0046 row as NOT RECORDED, never as a default", async () => {
    // The load-bearing case. Migration 0046 refuses to backfill because the
    // mode of an older row is genuinely unknown, and the column's whole job is
    // proving what happened. Rendering "strict" here would fabricate in the UI
    // exactly the record the migration declined to fabricate in the database.
    rows = [call({ redaction_mode: null })];
    await showAiTab();

    expect(screen.getByText("not recorded")).toBeInTheDocument();
    expect(screen.queryByText("strict")).not.toBeInTheDocument();
    expect(screen.queryByText("standard")).not.toBeInTheDocument();
    expect(screen.queryByText("off")).not.toBeInTheDocument();
  });

  it("marks a disabled-redactor call so it cannot be skimmed past", async () => {
    // `off` means the payload reached the provider unredacted. #144 exists
    // because that row was byte-identical to a clean one; surfacing the value
    // without distinguishing it would repeat the defect one layer up.
    rows = [call({ redaction_mode: "off" })];
    await showAiTab();

    const cell = screen.getByText("off");
    expect(cell).toBeInTheDocument();
    expect(cell.className).toMatch(/danger/);
    expect(cell).toHaveAttribute("title", expect.stringMatching(/unredacted/i));
  });

  it("does not colour an ordinary strict row", async () => {
    // The other half of the assertion above: if every row carried the danger
    // styling, the `off` test would pass while proving nothing about `off`.
    rows = [call({ redaction_mode: "strict" })];
    await showAiTab();

    expect(screen.getByText("strict").className).not.toMatch(/danger/);
  });

  it("shows the column header", async () => {
    rows = [call({})];
    await showAiTab();

    expect(
      screen.getByRole("columnheader", { name: /redaction/i }),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// #322 -- the details payload reaches a PERSON, not only the API.
//
// A run of accounting work landed on the premise that a discard is "reported
// somewhere a person reaches": #122's `entries_received` / `entries_written` /
// `discarded_entries` / `entries_write_check`, #132's `dropped_link_values` /
// `entries_unlinked_after_drops`, and earlier `rejected_enum_values`,
// `entries_without_tier`, `batches_failed`.
//
// All of it goes into `details`. All of it was reachable through
// `/admin/audit-entries` and NONE of it through this component, whose columns
// were When / Action / Target / Actor / Correlation. So "now visible" was true
// of the API and false of the UI, and a consultant looking at the audit tab
// after a run that discarded every entry saw a row identical to a clean one.
//
// These are RENDER-SIDE and were written BEFORE the component changed, so the
// failing state is the shipped one.
// ---------------------------------------------------------------------------

describe("AuditViewer details payload (#322)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders a discard counter that a clean row would not carry", async () => {
    mockEntries([
      entry({
        action: "risk_register.generated",
        details: {
          entries_received: 40,
          entries_written: 31,
          discarded_entries: { not_an_object: 9 },
        },
      }),
    ]);
    renderAuditEntries();

    // The VALUE, not merely the key: a column printing "details" and a dash
    // would satisfy a key-presence assertion and tell a reader nothing.
    //
    // Asserted as the whole rendered payload rather than as a bare `9`. A
    // first draft used /\b9\b/ and matched the row's own TIMESTAMP
    // ("9/20/2026") -- a pass-for-the-wrong-reason waiting to happen, and the
    // only reason it failed loudly is that TWO elements matched instead of
    // one.
    expect(await screen.findByText(/discarded_entries/)).toBeInTheDocument();
    expect(screen.getByText('{"not_an_object":9}')).toBeInTheDocument();
    expect(screen.getByText(/entries_written/)).toBeInTheDocument();
  });

  it("makes a run that discarded everything distinguishable from a clean one", async () => {
    // THE POINT OF THE ISSUE, asserted as a DIFFERENCE rather than as a
    // presence. Two rows, identical but for the payload; if the rendering
    // cannot tell them apart, the column exists and the defect does not move.
    mockEntries([
      entry({
        id: "00000000-0000-0000-0000-0000000000aa",
        action: "risk_register.generated",
        details: {
          entries_received: 9,
          entries_written: 0,
          entries_write_check: "MISMATCH",
        },
      }),
      entry({
        id: "00000000-0000-0000-0000-0000000000bb",
        action: "risk_register.generated",
        details: {
          entries_received: 9,
          entries_written: 9,
          entries_write_check: "agreed",
        },
      }),
    ]);
    renderAuditEntries();

    expect(await screen.findByText(/MISMATCH/)).toBeInTheDocument();
    expect(screen.getByText(/agreed/)).toBeInTheDocument();
  });

  it("says NOT RECORDED for a null payload rather than rendering nothing", async () => {
    // Absence and emptiness are different facts, and a blank cell reads as
    // "nothing was discarded" when it means "nothing was recorded". This repo
    // has the rule and the AuditViewer already applies it to `redaction_mode`.
    mockEntries([entry({ action: "csf.assessment.approved", details: null })]);
    renderAuditEntries();

    expect(await screen.findByText(/not recorded/i)).toBeInTheDocument();
  });

  it("shows the column header", async () => {
    mockEntries([
      entry({ action: "csf.assessment.approved", details: { a: 1 } }),
    ]);
    renderAuditEntries();

    expect(
      await screen.findByRole("columnheader", { name: /details/i }),
    ).toBeInTheDocument();
  });
});

describe("AuditViewer details truncation (#322)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("caps a long value rather than letting it set the row height", async () => {
    // `routes/risk.py` stores RAW model-authored strings in `details`
    // (`rejected_enum_values`, `dropped_link_values`) with no length bound --
    // `_coerce_enum` ends `return None, raw` and `_record` dedupes without
    // capping. This component is the surface that would otherwise render one.
    mockEntries([
      entry({
        action: "risk_register.generated",
        details: { rejected_enum_values: { likelihood: ["x".repeat(500)] } },
      }),
    ]);
    renderAuditEntries();

    expect(await screen.findByText(/rejected_enum_values/)).toBeInTheDocument();
    expect(screen.getByText(/\(\d+ chars\)/)).toBeInTheDocument();
    expect(
      screen.queryByText(new RegExp("x".repeat(300))),
    ).not.toBeInTheDocument();
  });

  it("says how many keys it did not show", async () => {
    const many: Record<string, unknown> = {};
    for (let i = 0; i < 40; i += 1) many[`k${i}`] = i;
    mockEntries([entry({ action: "risk_register.generated", details: many })]);
    renderAuditEntries();

    expect(await screen.findByText(/more keys not shown/)).toBeInTheDocument();
  });
});
