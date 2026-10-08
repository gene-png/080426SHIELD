import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ZtOmittedCapability, ZtRunAiResponse } from "@/lib/zt/types";

import { ZtRunAiAccounting } from "./ZtRunAiAccounting";

// #840: the capabilities a run got no entry for. Copy Z1 to Z6 is approved
// verbatim, so every assertion below is a literal string, never a regex built
// from the component. Fixture mode cannot reach any of this: the fixture
// answers every capability it is sent.

function nr(
  code: string,
  notes_blank: boolean,
  kept_stage: number | null,
): ZtOmittedCapability {
  return { capability_code: code, notes_blank, kept_stage };
}

/** A run that applied what it received and left `items` without a result. */
function result(
  items: ZtOmittedCapability[] | undefined,
  over: Partial<ZtRunAiResponse> = {},
): ZtRunAiResponse {
  return {
    changed: [],
    answers: [],
    suggestions_received: 4,
    suggestions_applied: 4,
    dropped: [],
    ...(items === undefined
      ? {}
      : { omitted_capabilities: items, omitted_count: items.length }),
    ...over,
  };
}

function paragraphs(container: HTMLElement): string[] {
  return [...container.querySelectorAll("p")].map((p) => p.textContent ?? "");
}

function listItems(container: HTMLElement): string[] {
  return [...container.querySelectorAll("li")].map(
    (li) => li.textContent ?? "",
  );
}

describe("ZtRunAiAccounting, capabilities with no result (#840)", () => {
  it("Z1, plural, and the two groups in order: blank notes, then notes", () => {
    const { container } = render(
      <ZtRunAiAccounting
        result={result([
          nr("ID.1", true, null),
          nr("ID.2", false, null),
          nr("ID.3", true, 2),
        ])}
      />,
    );
    const ps = paragraphs(container);
    const z1 = ps.indexOf("3 capabilities got no stage from the AI this run.");
    const z2 = ps.indexOf("No notes recorded (2):");
    const z3 = ps.indexOf(
      'Notes recorded, but no stage given (1). This includes notes such as "N/A" or "TBD":',
    );
    expect([z1, z2, z3].every((i) => i >= 0)).toBe(true);
    expect(z1 < z2 && z2 < z3).toBe(true);
    expect(listItems(container)).toEqual([
      "ID.1: no stage, so it stays unscored.",
      "ID.3: keeps stage 2, recorded earlier. This run did not confirm it.",
      "ID.2: no stage, so it stays unscored.",
    ]);
  });

  it("Z1, singular", () => {
    const { container } = render(
      <ZtRunAiAccounting result={result([nr("PR.4", true, null)])} />,
    );
    expect(paragraphs(container)).toContain(
      "1 capability got no stage from the AI this run.",
    );
    expect(paragraphs(container)).toContain("No notes recorded (1):");
  });

  it("Z4 and Z6 in the notes group, as an alert, only when a stage is kept there", () => {
    const { container } = render(
      <ZtRunAiAccounting
        result={result([nr("DS.1", false, 3), nr("DS.2", false, null)])}
      />,
    );
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(
      "DS.1: keeps stage 3, recorded earlier. This run did not confirm it.",
    );
    expect(alert).toHaveTextContent("DS.2: no stage, so it stays unscored.");
    expect(paragraphs(container)).toContain(
      "Check these before approving. A stage kept this way can come from a client's self-assessment and reaches the deliverable as it is.",
    );
  });

  it("no alert and no Z6 when no capability in the notes group kept a stage", () => {
    const { container } = render(
      <ZtRunAiAccounting
        // A kept stage in the BLANK group is neutral: the prompt leaves those
        // out by design.
        result={result([nr("DS.1", false, null), nr("DS.2", true, 2)])}
      />,
    );
    // Positive state first, so the absences below are not read mid-render.
    expect(paragraphs(container)).toContain(
      "2 capabilities got no stage from the AI this run.",
    );
    expect(screen.queryByRole("alert")).toBeNull();
    expect(
      paragraphs(container).some((p) => p.startsWith("Check these before")),
    ).toBe(false);
  });

  it("renders inside the received-0 branch, after its alert", () => {
    const { container } = render(
      <ZtRunAiAccounting
        result={result([nr("ID.1", true, null), nr("ID.2", true, null)], {
          suggestions_received: 0,
          suggestions_applied: 0,
        })}
      />,
    );
    const ps = paragraphs(container);
    expect(ps[0]).toMatch(/^The AI returned no suggestions at all/);
    expect(ps).toContain("2 capabilities got no stage from the AI this run.");
    expect(ps).toContain("No notes recorded (2):");
  });

  it.each([
    ["absent", undefined],
    ["0", [] as ZtOmittedCapability[]],
  ])("renders nothing when the field is %s", (_label, items) => {
    const { container } = render(<ZtRunAiAccounting result={result(items)} />);
    // Positive state first: the accounting headline rendered.
    expect(paragraphs(container)[0]).toMatch(/^AI applied 4 of 4/);
    expect(container.textContent).not.toContain("got no stage");
    expect(container.textContent).not.toContain("No notes recorded");
    expect(container.textContent).not.toContain("Notes recorded, but");
  });

  it.each([
    ["absent", undefined],
    ["0", [] as ZtOmittedCapability[]],
  ])(
    "renders nothing in the received-0 branch when the field is %s",
    (_label, items) => {
      const { container } = render(
        <ZtRunAiAccounting
          result={result(items, {
            suggestions_received: 0,
            suggestions_applied: 0,
          })}
        />,
      );
      expect(paragraphs(container)[0]).toMatch(
        /^The AI returned no suggestions at all/,
      );
      expect(container.textContent).not.toContain("got no stage");
    },
  );
});
