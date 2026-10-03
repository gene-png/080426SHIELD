import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DispositionHelp } from "./DispositionHelp";

// #642. The expected sentences come from the reader analysis on the issue, not
// from the component: only `cut` moves a number, `consolidate` counts no
// savings, and no other service reads a disposition.
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

  it("says a disposition does not reach ATT&CK, CSF, Zero Trust or Risk", () => {
    render(<DispositionHelp />);
    const help = screen.getByTestId("disposition-help");
    expect(help).toHaveTextContent(
      "A disposition does not change ATT&CK coverage, and nothing in CSF, Zero Trust or the Risk Register reads it.",
    );
    expect(help).toHaveTextContent(
      "A tool marked Cut still counts toward ATT&CK coverage.",
    );
  });
});
