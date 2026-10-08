import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type {
  ExtractionFinding,
  ExtractionFlagCounts,
} from "@/lib/tech_debt/types";

import { ExtractionFindings } from "./ExtractionFindings";
import { ExtractionFlags } from "./ExtractionFlags";

/**
 * C6, for #806: the E1 lines over the api's `extraction_flags`. Every expected
 * string is written out here from the approved copy (issue 736, comment
 * 6068587667, over the plan's in 806/5984600764), never read from the
 * component.
 */

const ZERO: ExtractionFlagCounts = {
  name_missing: 0,
  confidence_off_scale: 0,
  category_off_list: 0,
  source_row_duplicated: 0,
};

describe("ExtractionFlags (#806, E1)", () => {
  it("gives one line per non-zero flag, in the approved copy", () => {
    render(
      <ExtractionFlags
        flags={{
          name_missing: 2,
          confidence_off_scale: 3,
          category_off_list: 4,
          source_row_duplicated: 5,
        }}
      />,
    );
    const items = screen.getAllByRole("listitem").map((li) => li.textContent);
    expect(items).toEqual([
      '2 rows came back without a name and are listed as "Unknown capability".',
      "3 rows came back with a confidence the extraction does not use (only 100, 90 or 60).",
      "4 rows came back with a category outside the standard list, and it was kept.",
      "5 source rows were turned into more than one capability.",
    ]);
  });

  it("says 1 in the singular", () => {
    render(
      <ExtractionFlags
        flags={{
          name_missing: 1,
          confidence_off_scale: 1,
          category_off_list: 1,
          source_row_duplicated: 1,
        }}
      />,
    );
    const items = screen.getAllByRole("listitem").map((li) => li.textContent);
    expect(items).toEqual([
      '1 row came back without a name and is listed as "Unknown capability".',
      "1 row came back with a confidence the extraction does not use (only 100, 90 or 60).",
      "1 row came back with a category outside the standard list, and it was kept.",
      "1 source row was turned into more than one capability.",
    ]);
  });

  it("shows only the flags that are not zero", () => {
    render(<ExtractionFlags flags={{ ...ZERO, category_off_list: 2 }} />);
    expect(screen.getByTestId("extraction-flags")).toBeVisible();
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
    expect(
      screen.getByTestId("extraction-flag-category_off_list").textContent,
    ).toBe(
      "2 rows came back with a category outside the standard list, and it was kept.",
    );
  });

  it("renders nothing at zero, and nothing when not measured", () => {
    render(
      <div>
        <p>Capability list</p>
        <ExtractionFlags flags={ZERO} />
        <ExtractionFlags flags={null} />
        <ExtractionFlags flags={undefined} />
      </div>,
    );
    // Positive state first, so the absence below is not vacuous.
    expect(screen.getByText("Capability list")).toBeVisible();
    expect(screen.queryByTestId("extraction-flags")).toBeNull();
    expect(screen.queryByText(/came back/)).toBeNull();
  });
});

describe("ExtractionFindings leaves a duplicated row to E1 (#806)", () => {
  const dup: ExtractionFinding = {
    source_row_index: 1,
    item_name: "Teams",
    field: "source_row_index",
    reason: "duplicated",
    value: "1",
  };

  it("does not call a kept duplicate a value that could not be stored", () => {
    render(
      <div>
        <p>Capability list</p>
        <ExtractionFindings readOnly={false} findings={[dup]} />
      </div>,
    );
    expect(screen.getByText("Capability list")).toBeVisible();
    expect(screen.queryByTestId("extraction-findings")).toBeNull();
  });

  it("still counts the other findings beside it", () => {
    render(
      <ExtractionFindings
        readOnly={false}
        findings={[
          dup,
          {
            source_row_index: 0,
            item_name: "Tool",
            field: "confidence_pct",
            reason: "not_whole",
            value: "2.5",
          },
        ]}
      />,
    );
    expect(
      screen.getByTestId("extraction-findings-not-editable").textContent,
    ).toBe(
      "1 value about the AI's confidence or the source row could not be stored as given and was left blank.",
    );
  });
});
