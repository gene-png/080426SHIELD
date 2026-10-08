import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ExtractionFinding } from "@/lib/tech_debt/types";

import { ExtractionFindings } from "./ExtractionFindings";

/**
 * #833 / #834: the extraction's findings, in the copy approved on issue 833.
 * Every expected string is written out here.
 */

function f(over: Partial<ExtractionFinding>): ExtractionFinding {
  return {
    source_row_index: 0,
    item_name: "Tool",
    field: "annual_cost_usd",
    reason: "unparseable",
    value: "1200/month",
    ...over,
  };
}

describe("ExtractionFindings (#833)", () => {
  it("lists each editable finding in the table's own words", () => {
    render(
      <ExtractionFindings
        readOnly={false}
        findings={[
          f({}),
          f({ field: "license_count", reason: "not_whole", value: "2.9" }),
          f({ field: "license_count", reason: "out_of_range", value: "-1" }),
          f({
            field: "name",
            reason: "truncated",
            value: "N".repeat(120),
            width: 255,
          }),
        ]}
      />,
    );
    const box = screen.getByTestId("extraction-findings");
    expect(box).toHaveTextContent(
      "4 values from the AI could not be stored as given:",
    );
    expect(box).toHaveTextContent(
      'Tool, Annual cost USD: "1200/month" is not a number, so it was left blank.',
    );
    expect(box).toHaveTextContent(
      "Tool, License count: 2.9 is not a whole number, so it was left blank.",
    );
    expect(box).toHaveTextContent(
      "Tool, License count: -1 is outside the allowed range, so it was left blank.",
    );
    expect(box).toHaveTextContent("Tool, Name: shortened to 255 characters.");
    expect(box).toHaveTextContent("Correct these in the table below.");
  });

  it("singularises one finding", () => {
    render(<ExtractionFindings readOnly={false} findings={[f({})]} />);
    expect(screen.getByTestId("extraction-findings")).toHaveTextContent(
      "1 value from the AI could not be stored as given:",
    );
  });

  it("gives confidence and source row their own line, naming no control", () => {
    render(
      <ExtractionFindings
        readOnly={false}
        findings={[
          f({ field: "confidence_pct", reason: "out_of_range", value: "101" }),
          f({ field: "source_row_index", reason: "not_whole", value: "2.9" }),
        ]}
      />,
    );
    expect(
      screen.getByTestId("extraction-findings-not-editable").textContent,
    ).toBe(
      "2 values about the AI's confidence or the source row could not be stored as given and were left blank.",
    );
    // Neither reaches the list that says "Correct these in the table below".
    expect(screen.getByTestId("extraction-findings")).not.toHaveTextContent(
      "Correct these in the table below.",
    );
  });

  it("singularises the not-editable line", () => {
    render(
      <ExtractionFindings
        readOnly={false}
        findings={[
          f({ field: "confidence_pct", reason: "not_whole", value: "2.5" }),
        ]}
      />,
    );
    expect(
      screen.getByTestId("extraction-findings-not-editable").textContent,
    ).toBe(
      "1 value about the AI's confidence or the source row could not be stored as given and was left blank.",
    );
  });

  it("names no control on a released list", () => {
    render(<ExtractionFindings readOnly findings={[f({})]} />);
    // The finding still shows (the positive state) before the absence.
    expect(screen.getByTestId("extraction-findings")).toHaveTextContent(
      'Tool, Annual cost USD: "1200/month" is not a number',
    );
    expect(screen.getByTestId("extraction-findings")).not.toHaveTextContent(
      "Correct these in the table below.",
    );
  });

  it("states a rounded cost, in the approved copy", () => {
    render(
      <ExtractionFindings
        readOnly={false}
        findings={[f({ reason: "rounded", value: "12.345" })]}
      />,
    );
    expect(screen.getByTestId("extraction-findings")).toHaveTextContent(
      "Tool, Annual cost USD: 12.345 was rounded to whole cents.",
    );
  });

  it("says a reason it does not know rather than dropping it", () => {
    render(
      <ExtractionFindings
        readOnly={false}
        findings={[f({ reason: "source_row_duplicated", field: "name" })]}
      />,
    );
    expect(screen.getByTestId("extraction-findings")).toHaveTextContent(
      "Tool, Name: source_row_duplicated.",
    );
  });

  it("shows editable and not-editable findings together, each in its place", () => {
    render(
      <ExtractionFindings
        readOnly={false}
        findings={[
          f({}),
          f({ field: "confidence_pct", reason: "out_of_range", value: "101" }),
        ]}
      />,
    );
    const box = screen.getByTestId("extraction-findings");
    expect(box).toHaveTextContent(
      "1 value from the AI could not be stored as given:",
    );
    expect(box).toHaveTextContent(
      'Tool, Annual cost USD: "1200/month" is not a number, so it was left blank.',
    );
    expect(box).toHaveTextContent("Correct these in the table below.");
    expect(
      screen.getByTestId("extraction-findings-not-editable").textContent,
    ).toBe(
      "1 value about the AI's confidence or the source row could not be stored as given and was left blank.",
    );
    // The not-editable finding is counted in its own line, never in R1's.
    expect(box).not.toHaveTextContent("2 values from the AI");
  });

  it("says nothing for an empty or unrecorded list", () => {
    const { container: empty } = render(
      <ExtractionFindings readOnly={false} findings={[]} />,
    );
    expect(empty.textContent).toBe("");
    // No empty box either: a rendered-but-blank block reads as a finding.
    expect(screen.queryByTestId("extraction-findings")).toBeNull();
    const { container: unrecorded } = render(
      <ExtractionFindings readOnly={false} findings={null} />,
    );
    expect(unrecorded.textContent).toBe("");
  });
});
