import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type {
  AttackDashboardData,
  DashTechnique,
} from "@/lib/dashboards/attack";

import { AttackDashboard } from "./AttackDashboard";
import { AttackBlindCategory } from "./AttackBlindCategory";

/**
 * #1180: "What you're blind to today" lists categories, each opening its own
 * page. Copy B-1 to B-4 and "Each technique is listed under its first
 * tactic." approved verbatim (#736 comment 6216024281); literals below.
 */

function tech(partial: Partial<DashTechnique>): DashTechnique {
  return {
    code: "T0000",
    name: "Example",
    tactic_name: "Execution",
    status: "gap",
    detection_tools: [],
    prevention_tools: [],
    response_tools: [],
    rationale: null,
    computed_parent: false,
    sub_technique_count: 0,
    ...partial,
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
    service_id: "svc-1",
    service_title: "ATT&CK",
    released_at: "2026-05-12T00:00:00Z",
    deliverable_version: 1,
    rollup: {
      total_evaluated: techniques.length,
      covered: 0,
      partial: 0,
      gap: techniques.length,
      not_applicable: 0,
      outside_control_surface: 0,
      unable_to_determine: 0,
      coverage_pct: 0,
      coverage_measured: true,
      by_tactic: ["Execution", "Persistence", "Discovery"].map((name) => ({
        tactic_id: name,
        tactic_name: name,
        covered: 0,
        partial: 0,
        gap: 0,
        not_applicable: 0,
        unscored: 0,
        outside_control_surface: 0,
        unable_to_determine: 0,
        coverage_pct: 0,
        coverage_measured: false,
      })),
    },
    techniques,
  };
}

const WORLD = [
  tech({
    code: "T1059",
    name: "Command Interpreter",
    tactic_name: "Execution",
  }),
  tech({ code: "T1106", name: "Native API", tactic_name: "Execution" }),
  tech({ code: "T1136", name: "Create Account", tactic_name: "Persistence" }),
];

describe("the blind-spot categories on the dashboard (#1180)", () => {
  it("lists each category with its count, linking to its page", () => {
    render(<AttackDashboard data={data(WORLD)} />);
    const list = screen.getByTestId("attack-blind-categories");
    const links = within(list).getAllByRole("link");
    expect(links.map((a) => [a.textContent, a.getAttribute("href")])).toEqual([
      ["Execution (2)", "/dashboards/attack/svc-1/blind/execution"],
      ["Persistence (1)", "/dashboards/attack/svc-1/blind/persistence"],
    ]);
    expect(screen.getByTestId("attack-blind-first-tactic")).toHaveTextContent(
      "Each technique is listed under its first tactic.",
    );
    // The section's own count is the categories' sum.
    expect(screen.getByText("3 uncovered")).toBeInTheDocument();
  });
});

describe("AttackBlindCategory (#1180)", () => {
  it("shows that category's techniques under its heading, with a way back", () => {
    render(<AttackBlindCategory data={data(WORLD)} slug="execution" />);
    expect(
      screen.getByRole("heading", {
        name: "What you're blind to today: Execution",
      }),
    ).toBeInTheDocument();
    const cards = screen.getByTestId("attack-blind-category-cards");
    expect(within(cards).getByText("T1059")).toBeInTheDocument();
    expect(within(cards).getByText("T1106")).toBeInTheDocument();
    expect(within(cards).queryByText("T1136")).toBeNull();
    const back = screen.getByTestId("attack-blind-back");
    expect(back).toHaveTextContent("Back to the ATT&CK dashboard");
    expect(back).toHaveAttribute("href", "/dashboards/attack/svc-1");
  });

  it("says so for a category with nothing uncovered, with the way back", () => {
    render(<AttackBlindCategory data={data(WORLD)} slug="discovery" />);
    // Positive first: the page rendered its way back.
    expect(screen.getByTestId("attack-blind-back")).toHaveTextContent(
      "Back to the ATT&CK dashboard",
    );
    expect(screen.getByTestId("attack-blind-none")).toHaveTextContent(
      "No uncovered techniques in this category.",
    );
    expect(screen.queryByTestId("attack-blind-category-cards")).toBeNull();
  });

  it("refuses a slug that names no tactic, never saying nothing is uncovered", () => {
    // Review F1: B-4 over an unknown name is a false all-clear. The page
    // answers 404 first; this is the component's backstop.
    expect(() =>
      render(<AttackBlindCategory data={data(WORLD)} slug="defense-evasion" />),
    ).toThrow(/names no tactic/);
    expect(screen.queryByTestId("attack-blind-none")).toBeNull();
  });

  it("lists a computed parent's gap through its sub-techniques, not as a card", () => {
    // Review F2: the dashboard section renders no cards now, so the "no
    // Parent technique card" check belongs on the page that renders them.
    const parent = tech({
      code: "T1001",
      name: "Parent technique",
      tactic_name: "Execution",
      computed_parent: true,
      sub_technique_count: 2,
    });
    const kid = tech({
      code: "T1001.001",
      name: "Kid",
      tactic_name: "Execution",
    });
    render(<AttackBlindCategory data={data([parent, kid])} slug="execution" />);
    const cards = screen.getByTestId("attack-blind-category-cards");
    // Positive first: the sub-technique is listed.
    expect(within(cards).getByText("T1001.001")).toBeInTheDocument();
    expect(within(cards).queryByText("Parent technique")).toBeNull();
    expect(within(cards).queryByText("T1001")).toBeNull();
  });
});
