import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { AttackRunAiResponse } from "@/lib/attack/types";

import { AttackCitationAccounting } from "./AttackCitationAccounting";

/**
 * #1047: the run asks a second time about the techniques a successful batch
 * left out, and the panel says so. Copy R-1047-1 approved verbatim (#736
 * comment 6206422365). Every expected string below is a literal typed from
 * that ruling, never read from the component.
 */
function result(over: Partial<AttackRunAiResponse>): AttackRunAiResponse {
  return {
    tools_available: 3,
    changed: [],
    coverage: [],
    citations_confirmed: 4,
    citations_needs_review: 0,
    citations_rejected: 0,
    ...over,
  };
}

function lineFor(over: Partial<AttackRunAiResponse>): string {
  render(<AttackCitationAccounting result={result(over)} />);
  return screen.getByTestId("attack-reask").textContent ?? "";
}

describe("AttackCitationAccounting: the re-ask line (#1047)", () => {
  it.each([
    ["zero", { reasked_count: 0, reask_batches_total: 0 }],
    ["absent (a run stored before #1047)", {}],
  ])("renders nothing when the re-asked count is %s", (_label, over) => {
    render(<AttackCitationAccounting result={result(over)} />);
    // The positive state first: the panel rendered.
    expect(screen.getByTestId("attack-citation-accounting")).toHaveTextContent(
      /4 tool citations checked against/,
    );
    expect(screen.queryByTestId("attack-reask")).toBeNull();
  });

  it("says one technique was asked about again, in the singular", () => {
    expect(
      lineFor({
        reasked_count: 1,
        reask_batches_total: 1,
        reask_batches_failed: 0,
      }),
    ).toBe("1 technique the AI left out was asked about again.");
  });

  it("says how many were asked about again, comma-formatted, with no failure clause when none failed", () => {
    expect(
      lineFor({
        reasked_count: 1234,
        reask_batches_total: 50,
        reask_batches_failed: 0,
      }),
    ).toBe("1,234 techniques the AI left out were asked about again.");
  });

  it("adds how many follow-up requests failed when any did", () => {
    expect(
      lineFor({
        reasked_count: 37,
        reask_batches_total: 2,
        reask_batches_failed: 1,
      }),
    ).toBe(
      "37 techniques the AI left out were asked about again. 1 of 2 of those follow-up requests failed, so those techniques are still listed above as left out.",
    );
  });

  it("comma-formats the failure counts too", () => {
    expect(
      lineFor({
        reasked_count: 30000,
        reask_batches_total: 1200,
        reask_batches_failed: 1001,
      }),
    ).toBe(
      "30,000 techniques the AI left out were asked about again. 1,001 of 1,200 of those follow-up requests failed, so those techniques are still listed above as left out.",
    );
  });
});
