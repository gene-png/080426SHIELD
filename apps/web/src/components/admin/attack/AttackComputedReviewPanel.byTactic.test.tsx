import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type {
  AttackAssessment,
  AttackCatalog,
  AttackCoverageRow,
} from "@/lib/attack/types";

import { AttackComputedReviewPanel } from "./AttackComputedReviewPanel";

/**
 * #1052: the computed-status review queue, grouped by tactic, with a bulk
 * accept per tactic beside "Mark all". #1051 (first half): each technique
 * reads with its catalog name beside its code.
 *
 * The group heading, the per-tactic button and the multi-tactic note are
 * PLACEHOLDER copy (M-4a, M-4b, M-4c on #736) until approved, so these tests
 * pin structure, order, counts and what each button sends, not wording. The
 * tactic and technique names come from the catalog this file builds.
 */

function row(
  code: string,
  status: AttackCoverageRow["status"],
  computed: AttackCoverageRow["status"],
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
  };
}

function assessment(coverage: AttackCoverageRow[]): AttackAssessment {
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
  };
}

// Tactic order in the catalog is deliberately NOT alphabetical, so a test
// that passes on sorted names would fail here.
const CATALOG: AttackCatalog = {
  tactics: [
    {
      id: "TA0006",
      shortname: "credential-access",
      name: "Credential Access",
      description: "",
    },
    {
      id: "TA0011",
      shortname: "command-and-control",
      name: "Command and Control",
      description: "",
    },
  ],
  techniques: [
    {
      id: "T1003.001",
      name: "LSASS Memory",
      tactics: ["credential-access"],
      parent_id: "T1003",
      is_sub_technique: true,
    },
    {
      id: "T1003.002",
      name: "Security Account Manager",
      tactics: ["credential-access"],
      parent_id: "T1003",
      is_sub_technique: true,
    },
    {
      id: "T1001.001",
      name: "Junk Data",
      tactics: ["command-and-control"],
      parent_id: "T1001",
      is_sub_technique: true,
    },
    {
      id: "T1078.001",
      name: "Default Accounts",
      tactics: ["command-and-control", "credential-access"],
      parent_id: "T1078",
      is_sub_technique: true,
    },
  ],
  coverage_definitions: [],
  reason_codes: [],
  total_techniques: 4,
  total_sub_techniques: 4,
};

function groups(): HTMLElement[] {
  return screen.getAllByTestId("attack-computed-review-group");
}

function codesIn(group: HTMLElement): string[] {
  return within(group)
    .getAllByRole("row")
    .slice(1) // the header row
    .map((r) => within(r).getAllByRole("cell")[0].textContent ?? "");
}

describe("AttackComputedReviewPanel: by tactic (#1052) and names (#1051)", () => {
  it("groups the queue by tactic in catalog order, each technique with its name", () => {
    render(
      <AttackComputedReviewPanel
        assessment={assessment([
          row("T1001.001", "covered", "gap"),
          row("T1003.002", "covered", "partial"),
          row("T1003.001", "partial", "gap"),
        ])}
        catalog={CATALOG}
        busy={false}
        onReview={vi.fn()}
      />,
    );
    const [first, second] = groups();
    expect(groups()).toHaveLength(2);
    expect(first).toHaveTextContent("Credential Access");
    expect(first).toHaveTextContent("2");
    expect(codesIn(first)).toEqual([
      "T1003.001 LSASS Memory",
      "T1003.002 Security Account Manager",
    ]);
    expect(second).toHaveTextContent("Command and Control");
    expect(codesIn(second)).toEqual(["T1001.001 Junk Data"]);
  });

  it("a tactic's button sends exactly that tactic's codes, as shown", () => {
    const onReview = vi.fn();
    render(
      <AttackComputedReviewPanel
        assessment={assessment([
          row("T1001.001", "covered", "gap"),
          row("T1003.002", "covered", "partial"),
          row("T1003.001", "partial", "gap"),
        ])}
        catalog={CATALOG}
        busy={false}
        onReview={onReview}
      />,
    );
    const [credentialAccess] = groups();
    fireEvent.click(within(credentialAccess).getByRole("button"));
    expect(onReview).toHaveBeenCalledTimes(1);
    expect(onReview).toHaveBeenCalledWith([
      { code: "T1003.001", computed_status: "gap" },
      { code: "T1003.002", computed_status: "partial" },
    ]);
  });

  it("keeps Mark all, which still sends the whole queue once", () => {
    const onReview = vi.fn();
    render(
      <AttackComputedReviewPanel
        assessment={assessment([
          row("T1001.001", "covered", "gap"),
          row("T1003.001", "partial", "gap"),
          row("T1078.001", "partial", "gap"),
        ])}
        catalog={CATALOG}
        busy={false}
        onReview={onReview}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Mark all 3 as reviewed" }),
    );
    expect(onReview).toHaveBeenCalledWith([
      { code: "T1001.001", computed_status: "gap" },
      { code: "T1003.001", computed_status: "gap" },
      { code: "T1078.001", computed_status: "gap" },
    ]);
  });

  it("lists a technique under each of its tactics, and says so", () => {
    render(
      <AttackComputedReviewPanel
        assessment={assessment([
          row("T1003.001", "partial", "gap"),
          row("T1078.001", "partial", "gap"),
        ])}
        catalog={CATALOG}
        busy={false}
        onReview={vi.fn()}
      />,
    );
    const [credentialAccess, commandAndControl] = groups();
    expect(codesIn(credentialAccess)).toEqual([
      "T1003.001 LSASS Memory",
      "T1078.001 Default Accounts",
    ]);
    expect(codesIn(commandAndControl)).toEqual(["T1078.001 Default Accounts"]);
    expect(
      screen.getByTestId("attack-computed-review-multi-tactic"),
    ).toBeInTheDocument();
    // The status line counts techniques, not rows.
    expect(
      screen.getByText("0 reviewed, 2 awaiting review."),
    ).toBeInTheDocument();
  });

  it("says nothing about several tactics when no technique has more than one", () => {
    render(
      <AttackComputedReviewPanel
        assessment={assessment([row("T1003.001", "partial", "gap")])}
        catalog={CATALOG}
        busy={false}
        onReview={vi.fn()}
      />,
    );
    // The positive state first: the group rendered.
    expect(groups()).toHaveLength(1);
    expect(
      screen.queryByTestId("attack-computed-review-multi-tactic"),
    ).toBeNull();
  });

  it("disables every tactic button while another write is in flight", () => {
    render(
      <AttackComputedReviewPanel
        assessment={assessment([
          row("T1001.001", "covered", "gap"),
          row("T1003.001", "partial", "gap"),
        ])}
        catalog={CATALOG}
        busy={true}
        onReview={vi.fn()}
      />,
    );
    for (const group of groups()) {
      expect(within(group).getByRole("button")).toBeDisabled();
    }
  });

  it("shows the flat queue, every row, when the catalog does not name a queued technique", () => {
    // Nothing is dropped for want of a tactic: the ungrouped table is what
    // the panel showed before #1052.
    render(
      <AttackComputedReviewPanel
        assessment={assessment([
          row("T1003.001", "partial", "gap"),
          row("T9999", "partial", "gap"),
        ])}
        catalog={CATALOG}
        busy={false}
        onReview={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("attack-computed-review-group")).toBeNull();
    const table = screen.getByRole("table");
    expect(within(table).getByText("T9999")).toBeInTheDocument();
    expect(within(table).getByText("T1003.001")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Mark all 2 as reviewed" }),
    ).toBeInTheDocument();
  });
});
