import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ExtractionFinding } from "@/lib/tech_debt/types";

import { ExtractionFindings } from "./ExtractionFindings";

/**
 * TD-2 F2 (for #1058): a v3.3 flag (`is_suite`, `recognized`) the AI sent no
 * usable answer for. The table has no control for either, so the line names
 * none (D-076). Copy approved verbatim on #736 (comment 6170931492); every
 * expected string is written out here.
 */

const SINGULAR =
  "1 item is missing a usable answer from the AI on whether it is a suite or a recognized product, so it is shown as not answered.";

function flag(over: Partial<ExtractionFinding>): ExtractionFinding {
  return {
    source_row_index: 0,
    item_name: "Tool",
    field: "is_suite",
    reason: "missing",
    value: "None",
    ...over,
  };
}

function flagLine(): string | null {
  return screen.getByTestId("extraction-findings-flags").textContent;
}

describe("ExtractionFindings, the v3.3 flags (TD-2 F2)", () => {
  it("says one item is missing a usable answer, on its own line", () => {
    render(<ExtractionFindings readOnly={false} findings={[flag({})]} />);
    expect(flagLine()).toBe(SINGULAR);
    const box = screen.getByTestId("extraction-findings");
    // Not routed to the editable list, so no control is named.
    expect(box).not.toHaveTextContent("Correct these in the table below.");
    expect(box).not.toHaveTextContent("could not be stored as given");
    // The old raw form is gone.
    expect(box).not.toHaveTextContent("Tool, is_suite: missing.");
  });

  it("counts items, not flags: one item missing both counts once", () => {
    render(
      <ExtractionFindings
        readOnly={false}
        findings={[
          flag({}),
          flag({ field: "recognized", reason: "not_boolean", value: "true" }),
        ]}
      />,
    );
    expect(flagLine()).toBe(SINGULAR);
  });

  it("pluralises over distinct items, for either reason", () => {
    render(
      <ExtractionFindings
        readOnly={false}
        findings={[
          flag({}),
          flag({ field: "recognized" }),
          flag({
            source_row_index: 1,
            item_name: "Suite",
            field: "recognized",
            reason: "not_boolean",
            value: "1",
          }),
          flag({ source_row_index: 2, item_name: "Other", field: "is_suite" }),
        ]}
      />,
    );
    expect(flagLine()).toBe(
      "3 items are missing a usable answer from the AI on whether they are a suite or a recognized product, so they are shown as not answered.",
    );
  });

  it("puts no internal token on the panel", () => {
    render(
      <ExtractionFindings
        readOnly={false}
        findings={[
          flag({}),
          flag({
            source_row_index: 1,
            item_name: "Suite",
            field: "recognized",
            reason: "not_boolean",
            value: "1",
          }),
        ]}
      />,
    );
    // The positive state first, then the absences.
    expect(flagLine()).toContain("2 items are missing a usable answer");
    const text = screen.getByTestId("extraction-findings").textContent ?? "";
    for (const token of [
      "is_suite",
      "not_boolean",
      "missing:",
      "recognized:",
    ]) {
      expect(text).not.toContain(token);
    }
  });

  it("keeps an editable finding in its own list beside the flag line", () => {
    render(
      <ExtractionFindings
        readOnly={false}
        findings={[
          flag({}),
          flag({
            field: "annual_cost_usd",
            reason: "unparseable",
            value: "1200/month",
          }),
        ]}
      />,
    );
    const box = screen.getByTestId("extraction-findings");
    expect(box).toHaveTextContent(
      "1 value from the AI could not be stored as given:",
    );
    expect(box).toHaveTextContent("Correct these in the table below.");
    expect(flagLine()).toBe(SINGULAR);
    // The flag finding is not counted in the editable list's total.
    expect(box).not.toHaveTextContent("2 values from the AI");
  });

  it("says the flag line on a released list too, still naming no control", () => {
    render(<ExtractionFindings readOnly findings={[flag({})]} />);
    expect(flagLine()).toBe(SINGULAR);
    expect(screen.getByTestId("extraction-findings")).not.toHaveTextContent(
      "Correct these in the table below.",
    );
  });
});
