import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ZtRunAiResponse } from "@/lib/zt/types";

import { ZtRunAiAccounting } from "./ZtRunAiAccounting";

// #1084: a blank-notes capability is never sent, so an entry naming one is
// dropped as `no_notes`. That is the run working as designed, as in CSF
// (#1000): a by-design skip with its own label, never the red failure alert.

function result(over: Partial<ZtRunAiResponse> = {}): ZtRunAiResponse {
  return {
    changed: [],
    answers: [],
    suggestions_received: 0,
    suggestions_applied: 0,
    dropped: [],
    ...over,
  };
}

describe("ZtRunAiAccounting no_notes (#1084)", () => {
  it("lists a no_notes drop as a skip with its own label, not as a failure", () => {
    render(
      <ZtRunAiAccounting
        result={result({
          suggestions_received: 3,
          suggestions_applied: 2,
          dropped: [
            { reason: "no_notes", key: "ID-9", field: null, values: 1 },
          ],
        })}
      />,
    );
    // The positive state first, so the absence below is not vacuous.
    const items = screen.getAllByRole("listitem").map((li) => li.textContent);
    expect(
      items.some((t) =>
        /1 suggested value across 1 capability skipped.*capability has no notes, so the AI does not assess it/.test(
          t ?? "",
        ),
      ),
    ).toBe(true);
    expect(screen.queryByRole("alert")).toBeNull();
    // Never shown as a reason the client cannot read.
    expect(items.some((t) => /unrecognized reason/.test(t ?? ""))).toBe(false);
  });
});
