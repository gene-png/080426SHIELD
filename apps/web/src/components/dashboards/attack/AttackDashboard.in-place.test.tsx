import "@testing-library/jest-dom/vitest";

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type {
  AttackDashboardData,
  DashTechnique,
} from "@/lib/dashboards/attack";
import { dprCoverage } from "@/lib/dashboards/attack";

import { AttackDashboard } from "./AttackDashboard";

/**
 * #554 R3 on the CLIENT dashboard: what is in place, under each computed row's
 * chip; the techniques that cannot be prevented, in their own section; and the
 * awaiting-review sentence beside the percentage. The API sends the line and
 * the sentence; the section's copy is the approved text on #554, written out.
 */

const NP_HEADING = "Techniques that cannot be prevented";
const NP_SENTENCE =
  "MITRE ATT&CK lists no preventive control for these techniques, so they are assessed on detection and response. A technique here is Covered when it is both detected and responded to.";

function inPlace(
  detect: string,
  prevent: string,
  respond: string,
): NonNullable<DashTechnique["in_place"]> {
  return {
    detect,
    prevent,
    respond,
    line: `Detect: ${detect} · Prevent: ${prevent} · Respond: ${respond}`,
    cannot_be_prevented: prevent === "cannot be prevented",
  };
}

function technique(
  code: string,
  status: string,
  extra: Partial<DashTechnique> = {},
): DashTechnique {
  return {
    code,
    name: `Technique ${code}`,
    tactic_name: "Discovery",
    status: status as DashTechnique["status"],
    detection_tools: [],
    prevention_tools: [],
    response_tools: [],
    rationale: null,
    ...extra,
  };
}

function data(
  techniques: DashTechnique[],
  extra: Partial<AttackDashboardData> = {},
): AttackDashboardData {
  return {
    ai_source: {
      state: "live",
      sentence: "AI suggestions in this assessment came from a live AI model.",
      live_runs: 1,
      fixture_runs: 0,
    },
    service_id: "s1",
    service_title: "ATT&CK Coverage",
    released_at: "2026-09-01T12:00:00Z",
    deliverable_version: 1,
    parents_computed: true,
    rollup: {
      total_evaluated: 3,
      covered: 2,
      partial: 1,
      gap: 0,
      not_applicable: 0,
      outside_control_surface: 0,
      unable_to_determine: 0,
      coverage_pct: 83.3,
      coverage_measured: true,
      by_tactic: [],
    },
    techniques,
    ...extra,
  };
}

/** The code's row in the technique matrix: the one table row naming it that
 *  is not in the "cannot be prevented" section. */
function matrixRow(code: string): HTMLElement {
  const rows = screen
    .getAllByText(code)
    .map((el) => el.closest("tr"))
    .filter(
      (tr): tr is HTMLTableRowElement =>
        tr !== null &&
        tr.closest("table")?.getAttribute("aria-label") !== NP_HEADING,
    );
  if (rows.length !== 1)
    throw new Error(`${rows.length} matrix rows for ${code}`);
  return rows[0];
}

describe("AttackDashboard, #554 R3", () => {
  it("prints what is in place under a computed row's chip", () => {
    render(
      <AttackDashboard
        data={data([
          technique("T1003.001", "partial", {
            detection_tools: ["Tool D"],
            in_place: inPlace("in place", "not in place", "awaiting review"),
          }),
        ])}
      />,
    );
    expect(
      within(matrixRow("T1003.001")).getByText(
        "Detect: in place · Prevent: not in place · Respond: awaiting review",
      ),
    ).toBeInTheDocument();
  });

  it("prints no line on a row whose status was not computed", () => {
    render(
      <AttackDashboard data={data([technique("T1003.001", "partial")])} />,
    );
    const tr = matrixRow("T1003.001");
    expect(within(tr).getByText("Partial")).toBeInTheDocument();
    expect(within(tr).queryByText(/^Detect: /)).toBeNull();
  });

  it("lists the techniques that cannot be prevented in their own section", () => {
    render(
      <AttackDashboard
        data={data([
          technique("T1082", "covered", {
            in_place: inPlace("in place", "cannot be prevented", "in place"),
          }),
          technique("T1057", "partial", {
            in_place: inPlace(
              "in place",
              "cannot be prevented",
              "not in place",
            ),
          }),
          technique("T1003.001", "covered", {
            in_place: inPlace("in place", "in place", "in place"),
          }),
        ])}
      />,
    );
    const section = screen.getByRole("table", { name: NP_HEADING });
    expect(within(section).getByText("T1082")).toBeInTheDocument();
    expect(within(section).getByText("T1057")).toBeInTheDocument();
    expect(within(section).queryByText("T1003.001")).toBeNull();
    expect(screen.getByText(NP_SENTENCE)).toBeInTheDocument();
    expect(
      screen.getByText("These are 2 of the 3 assessed techniques above."),
    ).toBeInTheDocument();
  });

  it("counts one technique that cannot be prevented in the singular", () => {
    render(
      <AttackDashboard
        data={data([
          technique("T1082", "covered", {
            in_place: inPlace("in place", "cannot be prevented", "in place"),
          }),
        ])}
      />,
    );
    expect(
      screen.getByText("This is 1 of the 3 assessed techniques above."),
    ).toBeInTheDocument();
  });

  it("has no such section when every technique can be prevented", () => {
    render(
      <AttackDashboard
        data={data([
          technique("T1003.001", "covered", {
            in_place: inPlace("in place", "in place", "in place"),
          }),
        ])}
      />,
    );
    expect(matrixRow("T1003.001")).toBeInTheDocument(); // APPEAR first
    expect(screen.queryByRole("table", { name: NP_HEADING })).toBeNull();
  });

  it("puts the awaiting-review sentence beside the percentage", () => {
    const sentence =
      "1 technique lists tools awaiting review; it is scored as if those tools were not in place.";
    render(
      <AttackDashboard
        data={data([technique("T1003.001", "partial")], {
          awaiting_review_sentence: sentence,
        })}
      />,
    );
    expect(
      screen.getByText(
        (text) =>
          text.includes(
            "Weighted coverage across evaluated techniques: 83.3%.",
          ) && text.includes(sentence),
      ),
    ).toBeInTheDocument();
  });
});

describe("the triad on computed rows (#554 R3)", () => {
  it("counts a leg only when it is in place", () => {
    const triad = dprCoverage(
      [
        // Listed but awaiting review, and a technique that cannot be prevented:
        // neither leg is present, though both lists name a tool.
        technique("T1003.001", "partial", {
          detection_tools: ["Tool D"],
          prevention_tools: ["Tool P"],
          response_tools: ["Tool R"],
          in_place: inPlace("awaiting review", "in place", "in place"),
        }),
        technique("T1082", "covered", {
          detection_tools: ["Tool D"],
          prevention_tools: ["Tool P"],
          response_tools: ["Tool R"],
          in_place: inPlace("in place", "cannot be prevented", "in place"),
        }),
      ],
      true,
    );
    expect([triad.detect.n, triad.prevent.n, triad.respond.n]).toEqual([
      1, 1, 2,
    ]);
  });

  it("counts a non-empty tool list as before on a row that was not computed", () => {
    const triad = dprCoverage(
      [
        technique("T1003.001", "partial", {
          detection_tools: ["Tool D"],
          prevention_tools: [],
          response_tools: ["Tool R"],
        }),
      ],
      true,
    );
    expect([triad.detect.n, triad.prevent.n, triad.respond.n]).toEqual([
      1, 0, 1,
    ]);
  });
});
