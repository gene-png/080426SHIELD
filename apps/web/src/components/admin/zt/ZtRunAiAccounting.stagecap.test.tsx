import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ZtRunAiResponse } from "@/lib/zt/types";

import { ZtRunAiAccounting } from "./ZtRunAiAccounting";

// #839 F1: a Run-AI suggestion of a stage above the capability's own maximum is
// dropped as `stage_above_capability_max`. A reason with no label renders as an
// empty bullet (the count right, the explanation gone), so the label is pinned
// here, and the drop is a lost value, not a by-design skip.

function result(over: Partial<ZtRunAiResponse> = {}): ZtRunAiResponse {
  return {
    changed: [],
    answers: [],
    suggestions_received: 2,
    suggestions_applied: 1,
    dropped: [
      {
        reason: "stage_above_capability_max",
        key: "DOD.USR.01",
        field: "current",
        values: 1,
      },
    ],
    ...over,
  };
}

describe("ZtRunAiAccounting, a stage above the capability's maximum (#839)", () => {
  it("names the reason and counts it as lost", () => {
    render(<ZtRunAiAccounting result={result()} />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(/DOD\.USR\.01/);
    expect(alert).toHaveTextContent(
      /the capability has no DoD activities at that level, so it cannot be scored that stage/,
    );
  });
});
