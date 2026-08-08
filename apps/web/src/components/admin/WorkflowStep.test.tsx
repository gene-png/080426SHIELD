import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { WorkflowStep } from "./WorkflowStep";

/**
 * Shared by four admin workspaces, so the contract is worth pinning: a step
 * announces its position, explains itself, and when it cannot be acted on it
 * says which earlier step to go back to.
 */

describe("WorkflowStep", () => {
  it("puts the step number in the heading text, not only in the badge", () => {
    // The badge is aria-hidden decoration. Without the number in the heading a
    // screen-reader user hears an unordered pile of sections with no sequence.
    render(
      <WorkflowStep number={2} title="Review every technique" description="d">
        <span />
      </WorkflowStep>,
    );
    expect(
      screen.getByRole("heading", { name: "Step 2: Review every technique" }),
    ).toBeInTheDocument();
  });

  it("explains itself in the body, not just in a title", () => {
    render(
      <WorkflowStep
        number={1}
        title="Draft with AI"
        description="Claude drafts; you decide."
      >
        <span />
      </WorkflowStep>,
    );
    expect(screen.getByText("Claude drafts; you decide.")).toBeInTheDocument();
  });

  it("states WHY a step is blocked rather than presenting a dead control", () => {
    render(
      <WorkflowStep
        number={4}
        title="Generate the deliverable"
        description="d"
        blockedReason="Approve the assessment in step 3 first."
      >
        <button type="button">Generate</button>
      </WorkflowStep>,
    );
    expect(
      screen.getByText("Approve the assessment in step 3 first."),
    ).toBeInTheDocument();
    // The control stays in the DOM — the step owns the explanation, the caller
    // owns whether its own button is disabled.
    expect(
      screen.getByRole("button", { name: "Generate" }),
    ).toBeInTheDocument();
  });

  it("says nothing about blocking when the step is actionable", () => {
    render(
      <WorkflowStep number={1} title="Draft" description="d">
        <span />
      </WorkflowStep>,
    );
    expect(screen.queryByRole("note")).toBeNull();
  });

  it("marks a completed step in text, so completeness is not colour-only", () => {
    render(
      <WorkflowStep number={1} title="Draft" description="d" done>
        <span />
      </WorkflowStep>,
    );
    expect(
      screen.getByRole("heading", { name: "Step 1: Draft — done" }),
    ).toBeInTheDocument();
  });
});
