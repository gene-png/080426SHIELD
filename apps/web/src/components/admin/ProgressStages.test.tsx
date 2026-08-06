import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ProgressStages, type Stage } from "./ProgressStages";

/**
 * The bar is relabelling only — it renders state the API derived, and its one
 * piece of real logic is that `prepare` means something different for the two
 * services that have a client self-assessment step and the two that do not.
 */

const STAGES: Stage[] = [
  { key: "prepare", state: "complete" },
  { key: "analyze", state: "current" },
  { key: "review", state: "pending" },
  { key: "approve", state: "pending" },
  { key: "generate", state: "pending" },
  { key: "release", state: "pending" },
];

describe("ProgressStages", () => {
  it("names the client-input step for services that have one", () => {
    render(<ProgressStages stages={STAGES} kind="nist_csf" />);
    expect(screen.getByText("Self-assessment")).toBeInTheDocument();
    expect(screen.queryByText("Prepare")).not.toBeInTheDocument();
  });

  it("calls it Prepare for services with no self-assessment step", () => {
    // Tech Debt and ATT&CK never had a client-submission step, so no stage is
    // rendered permanently dead — the wording carries the difference instead.
    render(<ProgressStages stages={STAGES} kind="tech_debt" />);
    expect(screen.getByText("Prepare")).toBeInTheDocument();
    expect(screen.queryByText("Self-assessment")).not.toBeInTheDocument();
  });

  it("renders all six stages in order", () => {
    render(<ProgressStages stages={STAGES} kind="attack_coverage" />);
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(6);
    expect(items.map((li) => li.textContent?.split(":")[0])).toEqual([
      "Prepare",
      "Analyze",
      "Review",
      "Approve",
      "Generate",
      "Release",
    ]);
  });

  it("states each stage's status in text, not colour alone", () => {
    render(<ProgressStages stages={STAGES} kind="tech_debt" />);
    const nav = screen.getByRole("navigation", { name: "Assessment progress" });
    // The dots are aria-hidden, so without this the bar would be meaningless to
    // a screen reader — a progress indicator that conveys nothing.
    expect(nav.textContent).toContain("completed");
    expect(nav.textContent).toContain("in progress");
    expect(nav.textContent).toContain("not started");
  });

  it("renders nothing when there are no stages", () => {
    const { container } = render(<ProgressStages stages={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
