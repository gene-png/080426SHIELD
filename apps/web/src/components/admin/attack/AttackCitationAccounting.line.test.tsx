import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { AttackRunAiResponse } from "@/lib/attack/types";

import { AttackCitationAccounting } from "./AttackCitationAccounting";

/**
 * #1181: Gene's plain-English citation line, replacing the numeric headline.
 * C-1 to C-5 approved verbatim (#736 comment 6216024281, from the proposal in
 * 6208173127). Every expected string below is a literal typed from that
 * ruling, never read from the component.
 */

const C1 =
  "For each attack technique, the AI listed which of the client's tools help stop it, spot it or respond to it. Each time it named a tool, we checked that the tool is really on the client's approved list, so the AI can't make one up.";

function result(over: Partial<AttackRunAiResponse>): AttackRunAiResponse {
  return {
    tools_available: 3,
    changed: [],
    coverage: [],
    citations_confirmed: 0,
    citations_needs_review: 0,
    citations_rejected: 0,
    ...over,
  };
}

function line(over: Partial<AttackRunAiResponse>): string {
  render(<AttackCitationAccounting result={result(over)} />);
  return screen.getByTestId("attack-citation-line").textContent ?? "";
}

describe("AttackCitationAccounting: the plain-English citation line (#1181)", () => {
  it("all on the list (C-1, C-2, C-3)", () => {
    expect(line({ citations_confirmed: 12 })).toBe(
      `${C1} We checked 12 of these. All 12 are on the list. None need a closer look and none were rejected.`,
    );
  });

  it("some need a closer look and some were rejected (C-4)", () => {
    expect(
      line({
        citations_confirmed: 9,
        citations_needs_review: 2,
        citations_rejected: 1,
      }),
    ).toBe(
      `${C1} We checked 12 of these. 9 are on the list. 2 need a closer look. 1 were rejected.`,
    );
  });

  it("words each zero part of C-4", () => {
    expect(line({ citations_needs_review: 3 })).toBe(
      `${C1} We checked 3 of these. None are on the list. 3 need a closer look. None were rejected.`,
    );
  });

  it("words a rejection with nothing needing a closer look", () => {
    expect(line({ citations_confirmed: 4, citations_rejected: 2 })).toBe(
      `${C1} We checked 6 of these. 4 are on the list. None need a closer look. 2 were rejected.`,
    );
  });

  it("nothing checked (C-5)", () => {
    expect(line({})).toBe(
      `${C1} The AI named no tools, so there was nothing to check.`,
    );
  });

  it("only the completed batches when one failed (C-2a)", () => {
    expect(
      line({
        citations_confirmed: 12,
        batches_total: 26,
        batches_failed: 6,
      }),
    ).toBe(
      `${C1} We checked 12 of these, from the batches that completed. All 12 are on the list. None need a closer look and none were rejected.`,
    );
  });

  it("comma-formats the counts", () => {
    expect(
      line({
        citations_confirmed: 1200,
        citations_needs_review: 1001,
        citations_rejected: 0,
      }),
    ).toBe(
      `${C1} We checked 2,201 of these. 1,200 are on the list. 1,001 need a closer look. None were rejected.`,
    );
  });

  it("drops the old numeric headline", () => {
    render(
      <AttackCitationAccounting result={result({ citations_confirmed: 7 })} />,
    );
    // The positive state first: the new line rendered.
    expect(screen.getByTestId("attack-citation-line")).toHaveTextContent(
      /We checked 7 of these\./,
    );
    expect(
      screen.getByTestId("attack-citation-accounting"),
    ).not.toHaveTextContent(/tool citations? checked against/);
  });
});
