import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuditViewer } from "./AuditViewer";
import type { LlmCallRow } from "@/lib/admin/audit";

vi.mock("@/lib/admin/audit", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/admin/audit")>();
  return {
    ...actual,
    fetchAuditEntries: vi.fn(async () => ({ entries: [], next_cursor: null })),
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
