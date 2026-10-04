import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { AttackRunAiResponse } from "@/lib/attack/types";

import { AttackCitationAccounting } from "./AttackCitationAccounting";

/**
 * #841: the run refuses every N/A the AI suggests, and the workspace says how
 * many, in the copy approved verbatim on issue 841 (comment 5983735013).
 */
function result(over: Partial<AttackRunAiResponse>): AttackRunAiResponse {
  return {
    tools_available: 3,
    changed: [],
    coverage: [],
    citations_confirmed: 4,
    citations_needs_review: 0,
    citations_rejected: 0,
    ...over,
  };
}

describe("AttackCitationAccounting: AI N/A refused (#841)", () => {
  it("says one technique was suggested as N/A and not applied", () => {
    render(<AttackCitationAccounting result={result({ not_applicable_refused: 1 })} />);
    expect(screen.getByTestId("attack-not-applicable-refused").textContent).toBe(
      "1 technique was suggested as N/A and not applied. Only a consultant can mark a technique N/A, in the technique panel.",
    );
  });

  it("counts several", () => {
    render(<AttackCitationAccounting result={result({ not_applicable_refused: 4 })} />);
    expect(screen.getByTestId("attack-not-applicable-refused").textContent).toBe(
      "4 techniques were suggested as N/A and not applied. Only a consultant can mark a technique N/A, in the technique panel.",
    );
  });

  it("says nothing when none was refused", () => {
    render(<AttackCitationAccounting result={result({ not_applicable_refused: 0 })} />);
    // The panel itself rendered (the positive state) before the absence.
    expect(screen.getByTestId("attack-citation-accounting")).toHaveTextContent(
      /4 tool citations checked against/,
    );
    expect(screen.queryByTestId("attack-not-applicable-refused")).toBeNull();
  });
});
