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

  it("no alert and no Z6 when no capability in either group kept a stage", () => {
    const { container } = render(
      <ZtRunAiAccounting
        result={result([nr("DS.1", false, null), nr("DS.2", true, null)])}
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

  it("Z3 is the only alert when nothing else on the panel is one", () => {
    render(<ZtRunAiAccounting result={result([nr("DS.1", false, 3)])} />);
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "DS.1: keeps stage 3, recorded earlier. This run did not confirm it.",
    );
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("Z3 is a polite status beside the failure alert: one assertive region", () => {
    render(
      <ZtRunAiAccounting
        result={result([nr("DS.1", false, 3)], {
          suggestions_received: 4,
          suggestions_applied: 3,
          dropped: [
            {
              reason: "out_of_range",
              key: "DS.9",
              field: "current",
              values: 1,
            },
          ],
        })}
      />,
    );
    const alerts = screen.getAllByRole("alert");
    expect(alerts).toHaveLength(1);
    expect(alerts[0]).toHaveTextContent(
      "1 suggested value could not be applied:",
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      "Check these before approving. A stage kept this way can come from a client's self-assessment and reaches the deliverable as it is.",
    );
  });

  it("Z3 is a polite status beside the headline alert", () => {
    render(
      <ZtRunAiAccounting
        result={result([nr("DS.1", false, 3)], {
          suggestions_received: 2,
          suggestions_applied: 0,
          dropped: [
            { reason: "unknown_field", key: "DS.9", field: "stage", values: 2 },
          ],
        })}
      />,
    );
    const alerts = screen.getAllByRole("alert");
    expect(alerts).toHaveLength(1);
    expect(alerts[0]).toHaveTextContent(/^AI applied 0 of 2/);
    expect(screen.getByRole("status")).toHaveTextContent(
      "DS.1: keeps stage 3, recorded earlier. This run did not confirm it.",
    );
  });

  it("Z3 is a polite status beside the received-0 alert", () => {
    render(
      <ZtRunAiAccounting
        result={result([nr("DS.1", false, 3)], {
          suggestions_received: 0,
          suggestions_applied: 0,
        })}
      />,
    );
    const alerts = screen.getAllByRole("alert");
    expect(alerts).toHaveLength(1);
    expect(alerts[0]).toHaveTextContent(
      /^The AI returned no suggestions at all/,
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      "DS.1: keeps stage 3, recorded earlier. This run did not confirm it.",
    );
  });

  function many(n: number, notesBlank: boolean): ZtOmittedCapability[] {
    return Array.from({ length: n }, (_, i) =>
      nr(`C.${String(i + 1).padStart(2, "0")}`, notesBlank, null),
    );
  }

  it("lists 10 items in a group with no remainder line", () => {
    const { container } = render(
      <ZtRunAiAccounting result={result(many(10, true))} />,
    );
    const items = listItems(container);
    expect(items).toHaveLength(10);
    expect(items[9]).toBe("C.10: no stage, so it stays unscored.");
    expect(container.textContent).not.toContain("more");
  });

  it("caps a group at 10 items, then 'and 1 more'", () => {
    const { container } = render(
      <ZtRunAiAccounting result={result(many(11, true))} />,
    );
    const items = listItems(container);
    expect(items).toHaveLength(11);
    expect(items[9]).toBe("C.10: no stage, so it stays unscored.");
    expect(items[10]).toBe("and 1 more");
    expect(paragraphs(container)).toContain("No notes recorded (11):");
  });

  it("caps each group on its own: 12 with notes ends 'and 2 more'", () => {
    const { container } = render(
      <ZtRunAiAccounting
        result={result([nr("B.01", true, null), ...many(12, false)])}
      />,
    );
    const items = listItems(container);
    expect(items).toEqual([
      "B.01: no stage, so it stays unscored.",
      ...many(10, false).map(
        (x) => `${x.capability_code}: no stage, so it stays unscored.`,
      ),
      "and 2 more",
    ]);
  });

  const Z6 =
    "Check these before approving. A stage kept this way can come from a client's self-assessment and reaches the deliverable as it is.";

  it("a blank-notes capability that kept a stage brings Z6, in the one assertive region", () => {
    const { container } = render(
      <ZtRunAiAccounting
        // A kept stage in the BLANK group: leaving it out is by design under
        // the #806 ZT prompt (A5), and the stage still reaches the deliverable
        // unconfirmed (#736 comment 6071261772).
        result={result([nr("DS.2", true, 2)])}
      />,
    );
    const alerts = screen.getAllByRole("alert");
    expect(alerts).toHaveLength(1);
    expect(alerts[0]).toHaveTextContent(Z6);
    // The blank group itself is neutral and not a live region.
    const item = screen.getByText(
      "DS.2: keeps stage 2, recorded earlier. This run did not confirm it.",
    );
    expect(item.closest("[role]")).toBeNull();
    expect(paragraphs(container)).toContain("No notes recorded (1):");
  });

  it("Z6 renders once when both groups kept a stage", () => {
    const { container } = render(
      <ZtRunAiAccounting
        result={result([nr("DS.1", false, 3), nr("DS.2", true, 2)])}
      />,
    );
    expect(paragraphs(container).filter((p) => p === Z6)).toHaveLength(1);
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "DS.1: keeps stage 3, recorded earlier. This run did not confirm it.",
    );
  });

  it("a blank-notes kept stage beside the failure alert is a polite status", () => {
    render(
      <ZtRunAiAccounting
        result={result([nr("DS.2", true, 2)], {
          suggestions_received: 4,
          suggestions_applied: 3,
          dropped: [
            {
              reason: "out_of_range",
              key: "DS.9",
              field: "current",
              values: 1,
            },
          ],
        })}
      />,
    );
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(screen.getByRole("status")).toHaveTextContent(Z6);
  });

  /** The notes group's container: the element holding Z3's heading. */
  function notesGroup(): HTMLElement {
    const heading = screen.getByText(/^Notes recorded, but no stage given/);
    const group = heading.parentElement;
    if (group === null) throw new Error("Z3 heading has no container");
    return group;
  }

  it("a blank kept stage beside a notes group that kept none: one alert, Z6 in it, notes group neutral", () => {
    render(
      <ZtRunAiAccounting
        result={result([
          nr("ID.1", true, null),
          nr("ID.2", false, null),
          nr("ID.3", true, 2),
        ])}
      />,
    );
    const alerts = screen.getAllByRole("alert");
    expect(alerts).toHaveLength(1);
    expect(alerts[0]).toHaveTextContent(Z6);
    expect(alerts[0]).toHaveTextContent(
      "ID.2: no stage, so it stays unscored.",
    );
    const blankKept = screen.getByText(
      "ID.3: keeps stage 2, recorded earlier. This run did not confirm it.",
    );
    expect(blankKept.closest("[role]")).toBeNull();
    expect(notesGroup()).toHaveClass("text-ink-secondary");
    expect(notesGroup()).not.toHaveClass("text-status-danger-fg");
  });

  it.each([
    ["kept a stage", 3, "text-status-danger-fg", "text-ink-secondary"],
    ["kept none", null, "text-ink-secondary", "text-status-danger-fg"],
  ] as const)(
    "Z3's colour: the notes group is danger only when a notes row %s",
    (_label, kept, is, isNot) => {
      render(
        <ZtRunAiAccounting
          // A blank kept stage too, so Z6 is on the panel in both cases and
          // the colour cannot follow "any kept" by accident.
          result={result([nr("DS.1", false, kept), nr("DS.2", true, 2)])}
        />,
      );
      expect(screen.getByRole("alert")).toHaveTextContent(Z6);
      expect(notesGroup()).toHaveClass(is);
      expect(notesGroup()).not.toHaveClass(isNot);
    },
  );
});
