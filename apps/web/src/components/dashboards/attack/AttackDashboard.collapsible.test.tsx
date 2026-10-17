import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type {
  AttackDashboardData,
  DashTechnique,
} from "@/lib/dashboards/attack";

import { AttackDashboard } from "./AttackDashboard";

/**
 * #1384: "Techniques that cannot be prevented" starts collapsed. Collapsing
 * hides the ROWS only: the heading, the explaining sentence and the "{n} of
 * the {m} assessed techniques" line stay visible, and the toggle itself names
 * the count. The toggle is a native <summary>, so a keyboard and a screen
 * reader operate it.
 */

const NP_HEADING = "Techniques that cannot be prevented";
const NP_SENTENCE =
  "MITRE ATT&CK lists no preventive control for these techniques, so they are assessed on detection and response. A technique here is Covered when it is both detected and responded to.";

function technique(code: string, cannotBePrevented: boolean): DashTechnique {
  const prevent = cannotBePrevented ? "cannot be prevented" : "in place";
  return {
    code,
    name: `Technique ${code}`,
    tactic_name: "Discovery",
    status: "covered",
    detection_tools: [],
    prevention_tools: [],
    response_tools: [],
    rationale: null,
    in_place: {
      detect: "in place",
      prevent,
      respond: "in place",
      line: `Detect: in place · Prevent: ${prevent} · Respond: in place`,
      cannot_be_prevented: cannotBePrevented,
      state: {
        detect: "in_place",
        prevent: cannotBePrevented ? "cannot_be_prevented" : "in_place",
        respond: "in_place",
      },
    },
  };
}

function data(techniques: DashTechnique[]): AttackDashboardData {
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
      covered: 3,
      partial: 0,
      gap: 0,
      not_applicable: 0,
      outside_control_surface: 0,
      unable_to_determine: 0,
      coverage_pct: 100,
      coverage_measured: true,
      by_tactic: [],
    },
    techniques,
  };
}

const TWO = data([
  technique("T1082", true),
  technique("T1057", true),
  technique("T1003.001", false),
]);

function npTable(): HTMLElement {
  // `hidden: true`: a collapsed table is still in the DOM; the test asks
  // whether it is VISIBLE, not whether it exists.
  return screen.getByRole("table", { name: NP_HEADING, hidden: true });
}

describe("AttackDashboard, #1384 collapsible cannot-be-prevented list", () => {
  it("starts collapsed: the rows are hidden", () => {
    render(<AttackDashboard data={TWO} />);
    const table = npTable();
    expect(table.closest("details")).not.toBeNull();
    expect(table.closest("details")).not.toHaveAttribute("open");
    expect(within(table).getByText("T1082")).not.toBeVisible();
    expect(within(table).getByText("T1057")).not.toBeVisible();
  });

  it("keeps the heading, the sentence and the count visible when collapsed", () => {
    render(<AttackDashboard data={TWO} />);
    expect(npTable()).not.toBeVisible(); // collapsed, so the next lines mean something
    expect(screen.getByRole("heading", { name: NP_HEADING })).toBeVisible();
    expect(screen.getByText(NP_SENTENCE)).toBeVisible();
    expect(
      screen.getByText("These are 2 of the 3 assessed techniques above."),
    ).toBeVisible();
  });

  it("names the count on the toggle, which is the details' summary", () => {
    render(<AttackDashboard data={TWO} />);
    const toggle = screen.getByText("Show the 2 techniques");
    expect(toggle.tagName).toBe("SUMMARY");
    expect(toggle).toBeVisible();
    expect(toggle.parentElement).toBe(npTable().closest("details"));
  });

  it("opens on the toggle, showing the rows and the hide label", async () => {
    render(<AttackDashboard data={TWO} />);
    fireEvent.click(screen.getByText("Show the 2 techniques"));
    const table = npTable();
    expect(table.closest("details")).toHaveAttribute("open");
    expect(within(table).getByText("T1082")).toBeVisible();
    expect(within(table).getByText("T1057")).toBeVisible();
    // The browser fires `toggle` as a queued task, so the label follows it.
    expect(await screen.findByText("Hide the 2 techniques")).toBeVisible();
    expect(
      screen.getByText("These are 2 of the 3 assessed techniques above."),
    ).toBeVisible();
  });

  it("names one technique in the singular", () => {
    render(
      <AttackDashboard
        data={data([technique("T1082", true), technique("T1057", false)])}
      />,
    );
    expect(screen.getByText("Show the 1 technique")).toBeVisible();
  });
});
