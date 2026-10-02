import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { AttackAssessment, AttackCoverageRow } from "@/lib/attack/types";

import { AttackComputedReviewPanel } from "./AttackComputedReviewPanel";

/**
 * #554 R3, the advisor's Q1 (2026-10-02, 22:20Z): the consultant's review queue
 * that holds back release. The copy is A1-A6 of the build plan posted on #554,
 * written out here, never imported. The release refusal names this panel by its
 * heading, so the heading is pinned too.
 */

const INTRO =
  "On this assessment, each technique's status is computed from its Detect, Prevent and Respond tools. These techniques' computed status differs from the AI's suggestion. The deliverable cannot be released until each has been reviewed.";

function row(
  code: string,
  status: AttackCoverageRow["status"],
  computed: AttackCoverageRow["status"],
  extra: Partial<AttackCoverageRow> = {},
): AttackCoverageRow {
  return {
    id: `id-${code}`,
    assessment_id: "a1",
    technique_code: code,
    status,
    reason_code: null,
    narrative: null,
    notes: null,
    evidence_artifact_id: null,
    answered_by: null,
    answered_at: null,
    computed_status: computed,
    capabilities: {
      detect: "in_place",
      prevent: "not_in_place",
      respond: "awaiting_review",
      line: "",
      awaiting_review: true,
      cannot_be_prevented: false,
    },
    in_review_queue: status !== computed,
    reviewed_status: null,
    ...extra,
  };
}

function assessment(
  coverage: AttackCoverageRow[],
  extra: Partial<AttackAssessment> = {},
): AttackAssessment {
  return {
    ai_source: {
      state: "live",
      sentence: "AI suggestions in this assessment came from a live AI model.",
      live_runs: 1,
      fixture_runs: 0,
    },
    id: "a1",
    service_id: "s1",
    version: 1,
    status: "approved",
    approved_at: null,
    approved_by: null,
    catalog_version: "19.2",
    catalog_current: true,
    statuses_computed: true,
    coverage,
    ...extra,
  };
}

describe("AttackComputedReviewPanel", () => {
  it("lists the queue and accepts exactly the codes it shows", () => {
    const onReview = vi.fn();
    render(
      <AttackComputedReviewPanel
        assessment={assessment([
          row("T1003.002", "covered", "partial"),
          row("T1003.001", "partial", "gap"),
          row("T1003.003", "gap", "gap"),
          row("T1003.004", "partial", "covered", {
            in_review_queue: false,
            reviewed_status: "covered",
          }),
        ])}
        busy={false}
        onReview={onReview}
      />,
    );
    expect(
      screen.getByRole("heading", { name: "Computed status review" }),
    ).toBeInTheDocument();
    expect(screen.getByText(INTRO)).toBeInTheDocument();
    expect(
      screen.getByText("1 reviewed, 2 awaiting review."),
    ).toBeInTheDocument();

    const table = screen.getByRole("table");
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((h) => h.textContent),
    ).toEqual([
      "Technique",
      "AI suggested",
      "Computed",
      "Detect",
      "Prevent",
      "Respond",
    ]);
    const first = within(table).getByText("T1003.001").closest("tr");
    if (!first) throw new Error("no row for T1003.001");
    expect(
      within(first)
        .getAllByRole("cell")
        .map((c) => c.textContent),
    ).toEqual([
      "T1003.001",
      "Partial",
      "Gap",
      "in place",
      "not in place",
      "awaiting review",
    ]);
    expect(within(table).queryByText("T1003.003")).toBeNull();

    fireEvent.click(
      screen.getByRole("button", { name: "Mark all 2 as reviewed" }),
    );
    expect(onReview).toHaveBeenCalledWith(["T1003.001", "T1003.002"]);
  });

  it("says one in the singular", () => {
    render(
      <AttackComputedReviewPanel
        assessment={assessment([row("T1003.001", "partial", "gap")])}
        busy={false}
        onReview={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("button", { name: "Mark 1 as reviewed" }),
    ).toBeInTheDocument();
  });

  it("says so when nothing differs", () => {
    render(
      <AttackComputedReviewPanel
        assessment={assessment([row("T1003.001", "gap", "gap")])}
        busy={false}
        onReview={vi.fn()}
      />,
    );
    expect(
      screen.getByText(
        "No technique's computed status differs from the AI's suggestion.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("disables the button while another write is in flight", () => {
    render(
      <AttackComputedReviewPanel
        assessment={assessment([row("T1003.001", "partial", "gap")])}
        busy={true}
        onReview={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("button", { name: "Mark 1 as reviewed" }),
    ).toBeDisabled();
  });

  it.each([
    ["an assessment approved before R3", { statuses_computed: false }],
    ["a released assessment", { status: "released" as const }],
  ])("renders nothing for %s", (_label, extra) => {
    const { container } = render(
      <AttackComputedReviewPanel
        assessment={assessment([row("T1003.001", "partial", "gap")], extra)}
        busy={false}
        onReview={vi.fn()}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
