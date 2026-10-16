import "@testing-library/jest-dom/vitest";

import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ZtOmittedCapability, ZtRunAiResponse } from "@/lib/zt/types";

import { ZtRunAiAccounting } from "./ZtRunAiAccounting";

// #1083: a capability with no notes is never sent (#1084), so it is never
// scored. The "No notes recorded" group says so, and names the remedy. The
// string is Z-1083-1 as proposed at #736 comment 6205228372: PENDING the
// advisor's ruling, so this literal changes with the ruling, never with the
// component.
const Z_1083_1 = (n: number): string =>
  `No notes recorded (${n}). The AI scores only capabilities that have notes, so these were not scored. To score them, record notes and run the AI again:`;

function nr(code: string, notes_blank: boolean): ZtOmittedCapability {
  return { capability_code: code, notes_blank, kept_stage: null };
}

function result(items: ZtOmittedCapability[]): ZtRunAiResponse {
  return {
    changed: [],
    answers: [],
    suggestions_received: 1,
    suggestions_applied: 1,
    dropped: [],
    omitted_capabilities: items,
    omitted_count: items.length,
  };
}

function paragraphs(container: HTMLElement): string[] {
  return [...container.querySelectorAll("p")].map((p) => p.textContent ?? "");
}

describe("ZtRunAiAccounting, blank notes are never scored (#1083)", () => {
  it("says why the blank-notes capabilities got no stage, and the remedy", () => {
    const { container } = render(
      <ZtRunAiAccounting
        result={result([nr("ID.1", true), nr("ID.3", true), nr("ID.2", false)])}
      />,
    );
    const ps = paragraphs(container);
    expect(ps).toContain("3 capabilities got no stage from the AI this run.");
    expect(ps).toContain(Z_1083_1(2));
    // The noted group is a different cause and keeps its own line.
    expect(
      ps.some((p) => p.startsWith("Notes recorded, but no stage given (1).")),
    ).toBe(true);
  });

  it("states the count it lists, singular included", () => {
    const { container } = render(
      <ZtRunAiAccounting result={result([nr("ID.1", true)])} />,
    );
    expect(paragraphs(container)).toContain(Z_1083_1(1));
  });

  it("is absent when every capability left out had notes", () => {
    const { container } = render(
      <ZtRunAiAccounting result={result([nr("ID.2", false)])} />,
    );
    // The positive state first, so the absence is not vacuous.
    expect(paragraphs(container)).toContain(
      "1 capability got no stage from the AI this run.",
    );
    expect(container.textContent).not.toContain("No notes recorded");
  });
});
