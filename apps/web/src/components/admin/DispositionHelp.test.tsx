import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DispositionHelp } from "./DispositionHelp";

// #642. The expected sentences come from the reader analysis on the issue, not
// from the component. Since #804, both kinds of cut move the savings number
// ("Cut" and "Cut, covered by another tool", stored `consolidate`); Keep and
// Undecided move nothing.
function effectOf(label: string): string {
  const term = screen.getByText(label, { selector: "dt" });
  return term.nextElementSibling?.textContent ?? "";
}

describe("DispositionHelp (#642)", () => {
  it("explains all four dispositions the table offers", () => {
    render(<DispositionHelp />);
    const terms = screen.getAllByRole("term").map((t) => t.textContent ?? "");
    expect(terms).toEqual([
      "Undecided",
      "Keep",
      "Cut, covered by another tool",
      "Cut",
    ]);
  });

  it("says both kinds of cut add to savings, and Keep and Undecided do not", () => {
    // #804, the advisor's ruling on #736: "Cut, covered by another tool"
    // counts the tool's full annual cost, as Cut does.
    render(<DispositionHelp />);
    expect(effectOf("Cut")).toContain(
      "Its annual cost is added to the estimated annual savings.",
    );
    expect(effectOf("Cut")).toContain("shown as a lower bound");
    expect(effectOf("Cut, covered by another tool")).toContain(
      "Its full annual cost is added to the estimated annual savings, as for Cut.",
    );
    expect(effectOf("Keep")).toContain("no figure changes");
    expect(effectOf("Undecided")).not.toContain("savings");
  });

  it("says how a disposition reaches ATT&CK, and that CSF, Zero Trust and Risk do not read it", () => {
    // #801, copy approved by the advisor 05:05Z (T1, T2): a cut tool is a
    // planned retirement in ATT&CK, counted today and not after planned changes.
    render(<DispositionHelp />);
    const help = screen.getByTestId("disposition-help");
    expect(help).toHaveTextContent(
      "Nothing in CSF, Zero Trust or the Risk Register reads it.",
    );
    expect(help).toHaveTextContent(
      "In ATT&CK a tool marked Cut, or Cut, covered by another tool, is labelled a planned retirement: it still counts toward today's coverage, and not toward the coverage after planned changes.",
    );
    expect(help).toHaveTextContent(
      "and, for Cut and Cut, covered by another tool, the ATT&CK coverage after planned changes.",
    );
  });
});
