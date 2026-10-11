import "@testing-library/jest-dom/vitest";

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type {
  AttackDashboardData,
  DashTechnique,
} from "@/lib/dashboards/attack";
import { dprCoverage, triadPopulationText } from "@/lib/dashboards/attack";

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

const STATE: Record<
  string,
  NonNullable<DashTechnique["in_place"]>["state"]["detect"]
> = {
  "in place": "in_place",
  "not in place": "not_in_place",
  "awaiting review": "awaiting_review",
  "cannot be prevented": "cannot_be_prevented",
};

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
    state: {
      detect: STATE[detect],
      prevent: STATE[prevent],
      respond: STATE[respond],
    },
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

describe("the triad reads machine values, not words (#554 R3)", () => {
  it("counts a leg by its state whatever the words say", () => {
    const t = technique("T1003.001", "covered", {
      in_place: {
        ...inPlace("in place", "in place", "in place"),
        // The display words change; the state does not.
        detect: "In place (renamed)",
        prevent: "In place (renamed)",
        respond: "In place (renamed)",
      },
    });
    const triad = dprCoverage([t], true);
    expect([triad.detect.n, triad.prevent.n, triad.respond.n]).toEqual([
      1, 1, 1,
    ]);
  });
});

describe("Prevent's denominator (#554 R3, ruling (a))", () => {
  const rows = [
    technique("T1082", "covered", {
      in_place: inPlace("in place", "cannot be prevented", "in place"),
    }),
    technique("T1003.001", "covered", {
      in_place: inPlace("in place", "in place", "in place"),
    }),
    technique("T1003.002", "partial", {
      in_place: inPlace("in place", "not in place", "in place"),
    }),
  ];

  it("leaves out a technique that cannot be prevented, and says so", () => {
    const triad = dprCoverage(rows, true);
    expect(triad.total).toBe(3);
    expect(triad.preventTotal).toBe(2);
    expect(triad.prevent).toEqual({ n: 1, pct: 50 });
    expect(triadPopulationText(triad)).toBe(
      "Over 3 techniques. Prevent is over 2 techniques: 1 that cannot be prevented is not counted for it.",
    );
  });

  it("names the count in the plural", () => {
    const triad = dprCoverage(
      [
        ...rows,
        technique("T1057", "partial", {
          in_place: inPlace("in place", "cannot be prevented", "not in place"),
        }),
      ],
      true,
    );
    expect(triadPopulationText(triad)).toBe(
      "Over 4 techniques. Prevent is over 2 techniques: 2 that cannot be prevented are not counted for it.",
    );
  });

  it("prints the Prevent card over its own denominator", () => {
    render(<AttackDashboard data={data(rows, { statuses_computed: true })} />);
    expect(screen.getByText(/1 of 2 techniques/)).toBeInTheDocument();
  });
});

describe("R3 copy beside the percentages (#554 R3)", () => {
  const sentence =
    "1 technique lists tools awaiting review; it is scored as if those tools were not in place.";
  const r3 = data(
    [
      technique("T1082", "covered", {
        in_place: inPlace("in place", "cannot be prevented", "in place"),
      }),
    ],
    { statuses_computed: true, awaiting_review_sentence: sentence },
  );

  it("puts the sentence beside the KPI and triad percentages too", () => {
    render(<AttackDashboard data={r3} />);
    // The donut, the KPI row and the triad: three sites.
    expect(screen.getAllByText((text) => text.includes(sentence))).toHaveLength(
      3,
    );
  });

  it("does not say a Covered technique needed all three", () => {
    render(<AttackDashboard data={r3} />);
    expect(
      screen.getByText(
        "Detection, prevention and response in place, or detection and response where MITRE ATT&CK lists no preventive control",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText((text) =>
        text.startsWith(
          "A technique is fully covered when detection, prevention and response are all in place, or detection and response where MITRE ATT&CK lists no preventive control.",
        ),
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Detection + prevention + response present"),
    ).toBeNull();
  });

  it("keeps the old words before R3", () => {
    render(
      <AttackDashboard data={data([technique("T1003.001", "covered")])} />,
    );
    expect(
      screen.getByText("Detection + prevention + response present"),
    ).toBeInTheDocument();
  });
});
