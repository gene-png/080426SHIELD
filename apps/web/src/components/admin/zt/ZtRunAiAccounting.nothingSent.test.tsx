import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ZtOmittedCapability, ZtRunAiResponse } from "@/lib/zt/types";

import { ZtRunAiAccounting } from "./ZtRunAiAccounting";

// #1084: every capability blank, so the run sent nothing and made no call.
// Receiving nothing is then the design, not a response that "did not match the
// shape": the panel shows the omitted disclosure without the red alert. A run
// stored before `capabilities_sent` existed keeps the alert.

function blank(code: string): ZtOmittedCapability {
  return { capability_code: code, notes_blank: true, kept_stage: null };
}

function result(over: Partial<ZtRunAiResponse> = {}): ZtRunAiResponse {
  return {
    changed: [],
    answers: [],
    suggestions_received: 0,
    suggestions_applied: 0,
    dropped: [],
    omitted_capabilities: [blank("ID.1"), blank("ID.2")],
    omitted_count: 2,
    ...over,
  };
}

const DRIFT = /The AI returned no suggestions at all/;
// PENDING the advisor's ruling: the proposed line for a run that sent nothing.
// It changes with the ruling, never with the component.
const NOTHING_SENT =
  "No capability was sent to the AI, because none had notes recorded when this run started.";

describe("ZtRunAiAccounting, a run that sent nothing (#1084)", () => {
  it("shows the omitted disclosure and no drift alert", () => {
    render(<ZtRunAiAccounting result={result({ capabilities_sent: 0 })} />);
    // The positive state first, so the absences below are not vacuous.
    expect(screen.getByText(NOTHING_SENT)).toBeInTheDocument();
    expect(
      screen.getByText("2 capabilities got no stage from the AI this run."),
    ).toBeInTheDocument();
    expect(screen.queryByText(DRIFT)).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("keeps the drift alert when the run sent capabilities and got nothing", () => {
    render(<ZtRunAiAccounting result={result({ capabilities_sent: 2 })} />);
    expect(screen.getByRole("alert")).toHaveTextContent(DRIFT);
  });

  it("keeps the drift alert for a run stored before the count existed", () => {
    render(<ZtRunAiAccounting result={result()} />);
    expect(screen.getByRole("alert")).toHaveTextContent(DRIFT);
  });
});

describe("ZtRunAiAccounting, nothing sent and nothing omitted (#1084)", () => {
  // Every row blank AND locked: nothing sent, nothing omitted (a locked row is
  // never omitted). The panel is never empty and never claims drift.
  it("says nothing was sent, with no drift alert and no empty panel", () => {
    render(
      <ZtRunAiAccounting
        result={result({
          capabilities_sent: 0,
          omitted_capabilities: [],
          omitted_count: 0,
        })}
      />,
    );
    expect(screen.getByText(NOTHING_SENT)).toBeInTheDocument();
    expect(screen.queryByText(DRIFT)).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
