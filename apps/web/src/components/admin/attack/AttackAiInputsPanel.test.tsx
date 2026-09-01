import "@testing-library/jest-dom/vitest";

import { render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as attackClient from "@/lib/attack/client";
import type {
  AttackAiInputSourceList,
  AttackAiInputs,
  AttackAiInputTotals,
} from "@/lib/attack/types";

import { AttackAiInputsPanel } from "./AttackAiInputsPanel";

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

// Fixtures spell every field out literally. Nothing here is computed from the
// component or from `@/lib/attack/types` defaults -- a fixture that derives its
// expected value from the thing under test cannot fail (#72, D-051).
function sourceList(
  over: Partial<AttackAiInputSourceList> = {},
): AttackAiInputSourceList {
  return {
    capability_list_id: "list-1",
    tech_debt_service_id: "svc-1",
    tech_debt_service_title: "Atlas Tech Debt",
    version: 1,
    status: "approved",
    is_latest_for_service: true,
    membership_from_snapshot: false,
    membership_stale: false,
    sent_count: 2,
    not_sent_count: 0,
    source_rows_total: 40,
    excluded_attribution: "complete",
    excluded_rows_named: 3,
    ...over,
  };
}

function totals(over: Partial<AttackAiInputTotals> = {}): AttackAiInputTotals {
  return {
    sent: 2,
    not_sent: 0,
    awaiting_signoff: 0,
    withheld_security_scope: 0,
    withheld_not_in_approved_snapshot: 0,
    excluded_rows_named: 3,
    lists_with_unknown_exclusions: 0,
    sent_without_source_document: 0,
    ...over,
  };
}

function inputs(over: Partial<AttackAiInputs> = {}): AttackAiInputs {
  return {
    service_id: "svc-attack",
    capabilities: [],
    not_sent: [],
    excluded: [],
    sources: [sourceList()],
    totals: totals(),
    ...over,
  };
}

function renderReady(payload: AttackAiInputs) {
  fetchAttackAiInputs.mockResolvedValue(payload);
  render(<AttackAiInputsPanel serviceId="svc-attack" />);
  return screen.findByTestId("attack-ai-inputs");
}

describe("AttackAiInputsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("the excluded_attribution tri-state", () => {
    // The reason this endpoint exists. `Reconciliation.attribution_complete` is
    // not persisted, so an empty `excluded_rows` is the stored form of BOTH
    // "nothing was excluded" and "attribution failed". Rendering the second as a
    // zero is the silent under-report the panel was built to end, and it is the
    // persuasive kind: a number a consultant would reasonably act on.

    it("renders `complete` as the named count", async () => {
      await renderReady(
        inputs({
          sources: [
            sourceList({
              excluded_attribution: "complete",
              excluded_rows_named: 3,
            }),
          ],
        }),
      );
      expect(
        screen.getByTestId("attack-ai-inputs-attribution-list-1"),
      ).toHaveTextContent("3 named");
    });

    it("renders `unknown` as words and NEVER as a digit", async () => {
      await renderReady(
        inputs({
          sources: [
            sourceList({
              capability_list_id: "list-unknown",
              excluded_attribution: "unknown",
              // The stored value under `unknown`. A `?? 0` or a bare
              // `{excluded_rows_named}` in the cell would render this as "0".
              excluded_rows_named: 0,
              // Deliberately null so the "of N uploaded" suffix cannot supply a
              // digit and let a broken cell pass the no-digit assertion below.
              source_rows_total: null,
            }),
          ],
          totals: totals({
            excluded_rows_named: 0,
            lists_with_unknown_exclusions: 1,
          }),
        }),
      );
      const cell = screen.getByTestId(
        "attack-ai-inputs-attribution-list-unknown",
      );
      expect(cell).toHaveTextContent("Not knowable");
      // The whole point, stated as an assertion rather than as a comment.
      expect(cell.textContent ?? "").not.toMatch(/\d/);
    });

    it("renders `not_recorded` as making no claim, not as zero", async () => {
      await renderReady(
        inputs({
          sources: [
            sourceList({
              capability_list_id: "list-old",
              excluded_attribution: "not_recorded",
              excluded_rows_named: 0,
              source_rows_total: null,
            }),
          ],
          totals: totals({ excluded_rows_named: 0 }),
        }),
      );
      const cell = screen.getByTestId("attack-ai-inputs-attribution-list-old");
      expect(cell).toHaveTextContent("Not recorded");
      expect(cell.textContent ?? "").not.toMatch(/\d/);
    });

    it("calls the named total a floor when any list cannot say what it dropped", async () => {
      // A total over an unknowable population is not self-describing -- the same
      // rule that makes a withheld count travel beside a coverage percentage.
      await renderReady(
        inputs({
          sources: [
            sourceList({ excluded_attribution: "complete" }),
            sourceList({
              capability_list_id: "list-2",
              excluded_attribution: "unknown",
              excluded_rows_named: 0,
            }),
          ],
          totals: totals({
            excluded_rows_named: 3,
            lists_with_unknown_exclusions: 1,
          }),
        }),
      );
      expect(
        screen.getByTestId("attack-ai-inputs-excluded-unknown"),
      ).toHaveTextContent(/cannot say what it dropped/);
      expect(
        screen.getByTestId("attack-ai-inputs-excluded-unknown"),
      ).toHaveTextContent(/at least 3 and is not knowable/);
    });

    it("claims every row is accounted for only when no list is unknown or unrecorded", async () => {
      await renderReady(inputs());
      // Positive first: the summary must be present before absence means
      // anything. CLAUDE.md -- assert what must appear before what must not.
      expect(screen.getByTestId("attack-ai-inputs-excluded")).toHaveTextContent(
        /Every source row is accounted for/,
      );
      expect(
        screen.queryByTestId("attack-ai-inputs-excluded-unknown"),
      ).toBeNull();
    });

    it("does not claim every row is accounted for when a list is unknown", async () => {
      await renderReady(
        inputs({
          sources: [
            sourceList({
              excluded_attribution: "unknown",
              excluded_rows_named: 0,
            }),
          ],
          totals: totals({
            excluded_rows_named: 0,
            lists_with_unknown_exclusions: 1,
          }),
        }),
      );
      const summary = screen.getByTestId("attack-ai-inputs-excluded");
      expect(summary).toHaveTextContent(/not knowable from what was stored/);
      expect(summary).not.toHaveTextContent(
        /Every source row is accounted for/,
      );
    });
  });

  describe("phases", () => {
    it("says it is still loading rather than showing an empty panel", async () => {
      // A hook returning null for BOTH "loading" and "failed" makes those the
      // same value, and a caller gating on it fails open the moment the box is
      // slow. The three phases are distinct states here, so this asserts the
      // loading one is reachable and named.
      let resolve!: (value: AttackAiInputs) => void;
      fetchAttackAiInputs.mockReturnValue(
        new Promise<AttackAiInputs>((res) => {
          resolve = res;
        }),
      );
      render(<AttackAiInputsPanel serviceId="svc-attack" />);
      expect(
        screen.getByTestId("attack-ai-inputs-loading"),
      ).toBeInTheDocument();
      expect(screen.queryByTestId("attack-ai-inputs")).toBeNull();
      expect(screen.queryByTestId("attack-ai-inputs-error")).toBeNull();
      resolve(inputs());
      await screen.findByTestId("attack-ai-inputs");
    });

    it("fails loudly on an error instead of rendering as nothing-was-dropped", async () => {
      fetchAttackAiInputs.mockRejectedValue(
        new attackClient.AttackProxyError(403, {
          error: { message: "Admin access required." },
        }),
      );
      render(<AttackAiInputsPanel serviceId="svc-attack" />);
      const alert = await screen.findByTestId("attack-ai-inputs-error");
      expect(alert).toHaveTextContent("Admin access required.");
      expect(alert).toHaveAttribute("role", "alert");
      // A vanished panel would read as "nothing was filtered", which is the
      // exact misreading the component exists to prevent.
      expect(screen.queryByTestId("attack-ai-inputs")).toBeNull();
    });

    it("reports the status when the error payload carries no message", async () => {
      fetchAttackAiInputs.mockRejectedValue(
        new attackClient.AttackProxyError(502, undefined),
      );
      render(<AttackAiInputsPanel serviceId="svc-attack" />);
      expect(
        await screen.findByTestId("attack-ai-inputs-error"),
      ).toHaveTextContent("HTTP 502");
    });
  });

  describe("the empty-inventory warning", () => {
    it("says a run would fabricate gaps when no list feeds the mapping", async () => {
      await renderReady(
        inputs({
          sources: [],
          totals: totals({ sent: 0, excluded_rows_named: 0 }),
        }),
      );
      expect(screen.getByTestId("attack-ai-inputs-no-lists")).toHaveTextContent(
        /Every technique would be reported as a gap/,
      );
    });

    it("warns when lists exist but every capability was filtered out", async () => {
      await renderReady(
        inputs({
          sources: [sourceList({ sent_count: 0, not_sent_count: 4 })],
          totals: totals({
            sent: 0,
            not_sent: 4,
            withheld_security_scope: 4,
          }),
        }),
      );
      expect(
        screen.getByTestId("attack-ai-inputs-none-sent"),
      ).toHaveTextContent(/No security capabilities will be sent/);
    });

    it("states that nothing was withheld rather than leaving it to be inferred", async () => {
      // The absence of a line reads as zero, so the zero case is written out.
      await renderReady(inputs());
      expect(screen.getByTestId("attack-ai-inputs-not-sent")).toHaveTextContent(
        /Nothing on those lists was withheld/,
      );
    });

    it("breaks the withheld total down by reason", async () => {
      await renderReady(
        inputs({
          totals: totals({
            not_sent: 5,
            withheld_security_scope: 2,
            withheld_not_in_approved_snapshot: 3,
          }),
        }),
      );
      const line = screen.getByTestId("attack-ai-inputs-not-sent");
      expect(line).toHaveTextContent(/2 ruled out of the security subset/);
      expect(line).toHaveTextContent(
        /3 absent from the membership frozen at approval/,
      );
    });
  });

  describe("a capability whose live row was deleted", () => {
    it("says its description is unreadable rather than empty", async () => {
      // #96. The snapshot entry is still sent under its own name and carries no
      // description, so an em-dash in the category cell would say
      // "uncategorised" where the truth is "we cannot look".
      await renderReady(
        inputs({
          capabilities: [
            {
              name: "Qualys VMDR",
              vendor: "Qualys",
              category: null,
              security_functions: [],
              awaiting_signoff: false,
              capability_list_id: "list-1",
              source_list_version: 1,
              source_document: null,
              live_row_missing: true,
            },
          ],
          totals: totals({ sent: 1, sent_without_source_document: 1 }),
        }),
      );
      const table = screen.getByTestId("attack-ai-inputs-table");
      expect(table).toHaveTextContent("Qualys VMDR");
      // Asserted over the CELLS, not the table's whole text. The row's badge
      // copy ("live row deleted — still citable…") contains an em-dash of its
      // own, so a table-wide `not.toHaveTextContent("—")` matches that prose
      // and fails over a correct render -- and would equally have PASSED over a
      // broken one had the badge been worded without a dash.
      const cells = within(table)
        .getAllByRole("cell")
        .map((c) => c.textContent);
      expect(cells).toEqual([
        "Qualys",
        "not readable",
        "not readable",
        "not readable",
      ]);
    });

    it("renders an em-dash for a live row that is merely uncategorised", async () => {
      // The other half of the pair. Without this, "not readable" everywhere
      // would pass the test above and lose the distinction it is named for.
      await renderReady(
        inputs({
          capabilities: [
            {
              name: "Splunk Enterprise",
              vendor: "Splunk",
              category: null,
              security_functions: [],
              awaiting_signoff: false,
              capability_list_id: "list-1",
              source_list_version: 1,
              source_document: null,
              live_row_missing: false,
            },
          ],
          totals: totals({ sent: 1, sent_without_source_document: 1 }),
        }),
      );
      const table = screen.getByTestId("attack-ai-inputs-table");
      expect(table).toHaveTextContent("Splunk Enterprise");
      const cells = within(table)
        .getAllByRole("cell")
        .map((c) => c.textContent);
      expect(cells).toEqual(["Splunk", "—", "—", "—"]);
      expect(table).not.toHaveTextContent(/not readable/);
    });
  });

  describe("list-level disclosures", () => {
    it("says a frozen membership is out of date and names the remedy", async () => {
      await renderReady(
        inputs({
          sources: [
            sourceList({
              membership_from_snapshot: true,
              membership_stale: true,
            }),
          ],
        }),
      );
      expect(screen.getByTestId("attack-ai-inputs-stale")).toHaveTextContent(
        /Re-approve the capability list/,
      );
    });

    it("says nothing about staleness when the snapshot matches", async () => {
      await renderReady(
        inputs({
          sources: [
            sourceList({
              membership_from_snapshot: true,
              membership_stale: false,
            }),
          ],
        }),
      );
      expect(
        screen.getByTestId("attack-ai-inputs-sources"),
      ).toBeInTheDocument();
      expect(screen.queryByTestId("attack-ai-inputs-stale")).toBeNull();
    });

    it("never shows one service's provenance under another's id", async () => {
      // The phase is stored WITH the service it describes and the effective
      // phase is derived, so the render after a serviceId change cannot show
      // the previous service's answer. Resetting it inside the effect instead
      // leaves exactly one render where it does -- and on a panel whose whole
      // job is saying which tools feed WHICH mapping, a stale-but-plausible
      // answer is worse than a spinner. This is the property; the lint rule
      // that forbids the other spelling is not.
      fetchAttackAiInputs.mockResolvedValueOnce(
        inputs({
          sources: [sourceList({ tech_debt_service_title: "Atlas Tech Debt" })],
        }),
      );
      // Never settles, so the assertion below reads the render immediately
      // after the prop change rather than the one after service B loads.
      fetchAttackAiInputs.mockReturnValueOnce(
        new Promise<AttackAiInputs>(() => {}),
      );

      const { rerender } = render(<AttackAiInputsPanel serviceId="svc-a" />);
      expect(await screen.findByTestId("attack-ai-inputs")).toHaveTextContent(
        "Atlas Tech Debt",
      );

      rerender(<AttackAiInputsPanel serviceId="svc-b" />);
      expect(
        screen.getByTestId("attack-ai-inputs-loading"),
      ).toBeInTheDocument();
      expect(screen.queryByText(/Atlas Tech Debt/)).toBeNull();
    });

    it("refetches when the service changes", async () => {
      fetchAttackAiInputs.mockResolvedValue(inputs());
      const { rerender } = render(<AttackAiInputsPanel serviceId="svc-a" />);
      await screen.findByTestId("attack-ai-inputs");
      rerender(<AttackAiInputsPanel serviceId="svc-b" />);
      await waitFor(() => {
        expect(fetchAttackAiInputs).toHaveBeenCalledTimes(2);
      });
      expect(fetchAttackAiInputs).toHaveBeenLastCalledWith("svc-b");
    });
  });
});
