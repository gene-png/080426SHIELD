import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { AttackRunAiResponse } from "@/lib/attack/types";

import { AttackCitationAccounting } from "./AttackCitationAccounting";

/**
 * #1047: the run asks a second time about the techniques a successful batch
 * left out, and the panel says so. The copy is a PLACEHOLDER (R-1047-1) until
 * it is approved on #736, so these tests pin when the line renders and the
 * three numbers it carries, not its wording.
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

describe("AttackCitationAccounting: the re-ask line (#1047)", () => {
  it.each([
    ["zero", { reasked_count: 0, reask_batches_total: 0 }],
    ["absent (a run stored before #1047)", {}],
  ])("renders nothing when the re-asked count is %s", (_label, over) => {
    render(<AttackCitationAccounting result={result(over)} />);
    // The positive state first: the panel rendered.
    expect(screen.getByTestId("attack-citation-accounting")).toHaveTextContent(
      /4 tool citations checked against/,
    );
    expect(screen.queryByTestId("attack-reask")).toBeNull();
  });

  it("states how many techniques were asked again, in how many requests, and how many failed", () => {
    render(
      <AttackCitationAccounting
        result={result({
          reasked_count: 37,
          reask_batches_total: 2,
          reask_batches_failed: 1,
        })}
      />,
    );
    const line = screen.getByTestId("attack-reask");
    expect(line).toHaveTextContent(/asked again 37/);
    expect(line).toHaveTextContent(/requests 2/);
    expect(line).toHaveTextContent(/failed 1/);
  });
});
