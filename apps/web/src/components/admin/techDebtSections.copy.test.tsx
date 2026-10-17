import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { listArtifacts } from "@/lib/intake/artifacts";
import type { ConsolidationPlanSummary } from "@/lib/tech_debt/types";

import { ConsolidationPlanCard } from "./ConsolidationPlanCard";
import { TD_SECTION_COPY } from "./techDebtSections";
import { IntakeDocumentsPanel } from "./IntakeDocumentsPanel";

vi.mock("@/lib/intake/artifacts", () => ({ listArtifacts: vi.fn() }));
vi.mock("@/components/admin/RunAiGuard", () => ({
  RunAiGuard: ({
    children,
  }: {
    children: (p: { onClick: () => void }) => React.ReactNode;
  }) => children({ onClick: () => undefined }),
}));

/**
 * #1376: two shared Tech Debt components name a place on the old page ("in
 * step 2", "the table above"). Shown in a section, that place is elsewhere,
 * so each names the section instead; outside a section, the old words stand.
 */
describe("Tech Debt copy that names a place, in a section (#1376)", () => {
  it("the documents panel sends Discard draft to Review", async () => {
    vi.mocked(listArtifacts).mockResolvedValue({
      items: [
        {
          id: "doc-a",
          title: "a.csv",
          mime_type: "text/csv",
          size_bytes: 1024,
          uploaded_at: "2026-09-26T00:00:00Z",
          origin: "client_upload",
        },
      ],
    } as never);
    render(
      <IntakeDocumentsPanel
        onExtract={() => undefined}
        extracting={false}
        draftSourceId="doc-a"
        inSection
      />,
    );
    expect(await screen.findByTestId("draft-source-hint")).toHaveTextContent(
      'The open draft was extracted from a.csv. To extract from another document, use "Discard draft" in Review first.',
    );
  });

  it("the consolidation plan points at the Review table", () => {
    const summary = {
      capability_list_id: "list-1",
      capability_list_version: 1,
      total_items: 2,
      keep_count: 1,
      consolidate_count: 0,
      cut_count: 1,
      undecided_count: 0,
      estimated_annual_savings: 100,
      savings_cost_known: true,
    } satisfies ConsolidationPlanSummary;
    const { rerender } = render(
      <ConsolidationPlanCard summary={summary} inSection />,
    );
    expect(
      screen.getByText(/^Each row in the Review table carries a disposition/),
    ).toBeVisible();
    expect(screen.queryByText(/table above/)).toBeNull();
    rerender(<ConsolidationPlanCard summary={summary} />);
    expect(
      screen.getByText(/^Each row in the table above carries a disposition/),
    ).toBeVisible();
  });
});

/**
 * The advisor's one change to the result card's outcome lines (#736
 * 6229125629): with ONE uploaded row the line is singular, and "is" follows a
 * count of one.
 */
describe("the result card's outcome lines, in the singular (#1376)", () => {
  const { allIncluded, someLeftOut } = TD_SECTION_COPY.result;

  it("one uploaded row, all included: 'The 1 uploaded row is in the list.'", () => {
    expect(allIncluded(1)).toBe("The 1 uploaded row is in the list.");
  });

  it("several uploaded rows, all included, keep the plural", () => {
    expect(allIncluded(4)).toBe("All 4 uploaded rows are in the list.");
  });

  it("applied 1 says 'is', asked 1 says 'row'", () => {
    expect(someLeftOut(1, 1)).toBe("1 of 1 uploaded row is in the list.");
    expect(someLeftOut(1, 5)).toBe("1 of 5 uploaded rows is in the list.");
  });

  it("applied 4 of 5 keeps 'are'", () => {
    expect(someLeftOut(4, 5)).toBe("4 of 5 uploaded rows are in the list.");
  });
});

/**
 * The Recommendations section has no control today, so its one "can do" line
 * promises none (advisor, #736 6229792065).
 */
describe("the Recommendations section's bullet (#1376)", () => {
  it("says there is nothing to do yet, naming no control", () => {
    expect(TD_SECTION_COPY.header.recommendations.canDo).toEqual([
      "Nothing to do yet: this section is empty until recommendations are built.",
    ]);
  });
});
