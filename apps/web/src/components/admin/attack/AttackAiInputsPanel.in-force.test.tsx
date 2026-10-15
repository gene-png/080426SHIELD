import "@testing-library/jest-dom/vitest";

import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as attackClient from "@/lib/attack/client";
import type {
  AttackAiInputSourceList,
  AttackAiInputs,
  AttackAiInputTotals,
} from "@/lib/attack/types";

import { AttackAiInputsPanel } from "./AttackAiInputsPanel";

// For #1012: only each Tech Debt list's version IN FORCE (R6b) is offered to
// the model, so the panel must say which version that is and name what the
// others hold. Every expected string is the copy written out, never imported.

vi.mock("@/lib/attack/client", () => ({
  AttackProxyError: class AttackProxyError extends Error {
    constructor(
      public readonly status: number,
      public readonly payload: unknown,
    ) {
      super(`ATT&CK proxy ${status}`);
    }
  },
  fetchAttackAiInputs: vi.fn(),
}));

const fetchAttackAiInputs = vi.mocked(attackClient.fetchAttackAiInputs);

// An approved v1 IN FORCE beside an open draft v2 that is the LATEST and NOT
// in force: the case where keying on "latest" says the wrong thing twice.
const V1: AttackAiInputSourceList = {
  capability_list_id: "list-v1",
  tech_debt_service_id: "svc-1",
  tech_debt_service_title: "Atlas Tech Debt",
  version: 1,
  status: "approved",
  is_latest_for_service: false,
  in_force: true,
  membership_from_snapshot: true,
  membership_stale: false,
  sent_count: 1,
  not_sent_count: 0,
  source_rows_total: 10,
  excluded_attribution: "complete",
  excluded_rows_named: 0,
};
const V2: AttackAiInputSourceList = {
  capability_list_id: "list-v2",
  tech_debt_service_id: "svc-1",
  tech_debt_service_title: "Atlas Tech Debt",
  version: 2,
  status: "draft",
  is_latest_for_service: true,
  in_force: false,
  membership_from_snapshot: false,
  membership_stale: false,
  sent_count: 0,
  not_sent_count: 1,
  source_rows_total: 10,
  excluded_attribution: "complete",
  excluded_rows_named: 0,
};
const TOTALS: AttackAiInputTotals = {
  sent: 1,
  not_sent: 1,
  awaiting_signoff: 0,
  withheld_security_scope: 0,
  withheld_not_in_approved_snapshot: 0,
  withheld_list_discarded: 0,
  withheld_version_not_in_force: 1,
  excluded_rows_named: 0,
  lists_with_unknown_exclusions: 0,
  sent_without_source_document: 0,
};
const PAYLOAD: AttackAiInputs = {
  service_id: "svc-attack",
  capabilities: [],
  not_sent: [
    {
      name: "SentinelOne Singularity",
      vendor: null,
      reason: "version_not_in_force",
      capability_list_id: "list-v2",
      source_list_version: 2,
      source_document: null,
    },
  ],
  excluded: [],
  sources: [V1, V2],
  totals: TOTALS,
};

async function renderReady(payload: AttackAiInputs) {
  fetchAttackAiInputs.mockResolvedValue(payload);
  render(<AttackAiInputsPanel serviceId="svc-attack" />);
  return screen.findByTestId("attack-ai-inputs");
}

describe("AttackAiInputsPanel, the version in force (#1012)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("counts the not-in-force reason in the breakdown", async () => {
    await renderReady(PAYLOAD);
    const line = screen.getByTestId("attack-ai-inputs-not-sent");
    expect(line).toHaveTextContent(/— 1 on a list version not in force\./);
    expect(line).not.toHaveTextContent(/for another reason/);
  });

  it("pills and explains the version not in force, never 'superseded'", async () => {
    await renderReady(PAYLOAD);
    expect(screen.getByText("Includes 1 version not in force")).toBeVisible();
    expect(
      screen.getByTestId("attack-ai-inputs-not-in-force").textContent,
    ).toBe(
      "Only the version in force of each Tech Debt list is offered to the model: its newest approved or released version that lists a security tool, or, when it has no approved or released version, its newest draft that does. A tool only another version holds is not offered.",
    );
    expect(screen.queryByText(/superseded/i)).toBeNull();
    expect(
      screen.queryByText(/Every non-discarded capability list counts/),
    ).toBeNull();
  });

  it("suffixes the version not in force, and not the one in force", async () => {
    await renderReady(PAYLOAD);
    const sources = screen.getByTestId("attack-ai-inputs-sources");
    expect(
      within(sources).getByRole("rowheader", {
        name: "Atlas Tech Debt v2 (not in force)",
      }),
    ).toBeInTheDocument();
    expect(
      within(sources).getByRole("rowheader", { name: "Atlas Tech Debt v1" }),
    ).toBeInTheDocument();
  });

  it("explains a withheld row with its own reason copy", async () => {
    await renderReady(PAYLOAD);
    const table = screen.getByTestId("attack-ai-inputs-not-sent-table");
    expect(table).toHaveTextContent(
      "On a version of its Tech Debt list that is not in force, so nothing on it is offered. Only each list's newest approved or released version that lists a security tool is offered, or, when the list has no approved or released version, its newest draft that does.",
    );
    expect(table).not.toHaveTextContent(/does not recognise/);
  });

  it("counts a LATEST version that is not in force (one with no security tool)", async () => {
    // A service whose only version lists no security tool has nothing in
    // force: that version is the latest AND not in force. Counting "not
    // latest" instead would print nothing here.
    await renderReady({
      ...PAYLOAD,
      not_sent: [],
      sources: [{ ...V2, sent_count: 0, not_sent_count: 0 }],
      totals: {
        ...TOTALS,
        sent: 0,
        not_sent: 0,
        withheld_version_not_in_force: 0,
      },
    });
    expect(screen.getByText("Includes 1 version not in force")).toBeVisible();
    expect(screen.getByTestId("attack-ai-inputs-not-in-force")).toBeVisible();
  });

  it("says nothing about versions when every version is in force", async () => {
    await renderReady({
      ...PAYLOAD,
      not_sent: [],
      sources: [{ ...V1, is_latest_for_service: true }],
      totals: { ...TOTALS, not_sent: 0, withheld_version_not_in_force: 0 },
    });
    expect(screen.getByTestId("attack-ai-inputs-sources")).toBeInTheDocument();
    expect(screen.queryByTestId("attack-ai-inputs-not-in-force")).toBeNull();
    expect(screen.queryByText(/not in force/)).toBeNull();
  });
});
