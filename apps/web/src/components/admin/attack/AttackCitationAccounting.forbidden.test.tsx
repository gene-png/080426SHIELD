import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { AttackRunAiResponse } from "@/lib/attack/types";

import { AttackCitationAccounting } from "./AttackCitationAccounting";

/**
 * #806 C4: the run refuses an AI Partial whose reason only a consultant may
 * give, and the workspace says how many techniques it refused (PR #951 review,
 * F2). The expected strings are literals, not read from the component.
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

describe("AttackCitationAccounting: forbidden partial reason refused (#806)", () => {
  it("says one technique was refused, in the singular", () => {
    render(
      <AttackCitationAccounting
        result={result({ forbidden_reason_refused: 1 })}
      />,
    );
    expect(
      screen.getByTestId("attack-forbidden-reason-refused").textContent,
    ).toBe(
      "1 technique was suggested as Partial with a reason only a consultant can give, so it was not applied and keeps the status it had. A consultant can set that reason in the technique panel.",
    );
  });

  it("counts several, in the plural", () => {
    render(
      <AttackCitationAccounting
        result={result({ forbidden_reason_refused: 3 })}
      />,
    );
    expect(
      screen.getByTestId("attack-forbidden-reason-refused").textContent,
    ).toBe(
      "3 techniques were suggested as Partial with a reason only a consultant can give, so they were not applied and keep the status they had. A consultant can set that reason in the technique panel.",
    );
  });

  it.each([
    ["zero", { forbidden_reason_refused: 0 }],
    ["absent", {}],
  ])("says nothing when the count is %s", (_label, over) => {
    render(<AttackCitationAccounting result={result(over)} />);
    // The panel itself rendered (the positive state) before the absence.
    expect(screen.getByTestId("attack-citation-accounting")).toHaveTextContent(
      /4 tool citations checked against/,
    );
    expect(screen.queryByTestId("attack-forbidden-reason-refused")).toBeNull();
  });
});
