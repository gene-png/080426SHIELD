import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AiResultCard } from "./AiResultCard";

describe("AiResultCard (for #1087)", () => {
  it("leads with the outcome: the card's text starts with it", () => {
    render(
      <AiResultCard tone="warning" outcome="40 of 45 rows scored">
        <p>DETAIL</p>
      </AiResultCard>,
    );
    const card = screen.getByTestId("ai-result-card");
    expect(card.textContent?.startsWith("40 of 45 rows scored")).toBe(true);
    expect(card.textContent).toBe("40 of 45 rows scoredDETAIL");
  });

  it("puts the outcome before the detail in the document", () => {
    render(
      <AiResultCard tone="success" outcome="OUTCOME">
        <p>DETAIL</p>
      </AiResultCard>,
    );
    const outcome = screen.getByText("OUTCOME");
    const detail = screen.getByText("DETAIL");
    expect(
      outcome.compareDocumentPosition(detail) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it.each([
    ["success", "status-success", ["status-warning", "status-danger"]],
    ["warning", "status-warning", ["status-success", "status-danger"]],
    ["failure", "status-danger", ["status-success", "status-warning"]],
  ] as const)(
    "tone %s is colour only (%s), with no words of its own",
    (tone, own, others) => {
      render(<AiResultCard tone={tone} outcome="X" />);
      const card = screen.getByTestId("ai-result-card");
      expect(card.textContent).toBe("X");
      expect(card.className).toContain(`bg-${own}-bg`);
      for (const other of others) expect(card.className).not.toContain(other);
    },
  );

  it.each(["", "   "])("refuses a blank outcome %j", (outcome) => {
    expect(() =>
      render(<AiResultCard tone="success" outcome={outcome} />),
    ).toThrow(/blank outcome/);
  });
});

// The advisor's approved labels (#736, issuecomment-6128447366), transcribed
// here literally, never imported from the component: this is the spec.
const ASKED = "Asked";
const APPLIED = "Applied";
const NOT_APPLIED = "Not applied";
const UNSCORED = "Unscored";
const WHAT_TO_DO_NEXT = "What to do next";

const FIGURES = {
  asked: 45,
  applied: 18,
  notApplied: 27,
  notAppliedReasons: [
    { reason: "R-NO-NOTES", count: 25 },
    { reason: "R-OUT-OF-RANGE", count: 2 },
  ],
  unscored: 0,
};

describe("AiResultCard figures and next step (rule 8, for #1087)", () => {
  it("renders outcome, then the four figures under the approved labels, then detail, then the next step", () => {
    render(
      <AiResultCard
        tone="warning"
        outcome="OUTCOME"
        figures={FIGURES}
        nextStep="NEXT-CONTENT"
      >
        <p>DETAIL</p>
      </AiResultCard>,
    );
    const card = screen.getByTestId("ai-result-card");
    expect(card.textContent).toBe(
      "OUTCOME" +
        `${ASKED}45` +
        `${APPLIED}18` +
        `${NOT_APPLIED}27R-NO-NOTES 25R-OUT-OF-RANGE 2` +
        `${UNSCORED}0` +
        "DETAIL" +
        `${WHAT_TO_DO_NEXT}NEXT-CONTENT`,
    );
    const terms = screen
      .getByTestId("ai-result-figures")
      .querySelectorAll("dt");
    expect([...terms].map((t) => t.textContent)).toEqual([
      ASKED,
      APPLIED,
      NOT_APPLIED,
      UNSCORED,
    ]);
    const next = screen.getByTestId("ai-result-next");
    expect(next.firstElementChild?.textContent).toBe(WHAT_TO_DO_NEXT);
  });

  it("puts each count under its own label, not just in order", () => {
    render(
      <AiResultCard
        tone="success"
        outcome="X"
        figures={{ asked: 4, applied: 3, notApplied: 2, unscored: 1 }}
      />,
    );
    const valueOf = (label: string) =>
      screen.getByText(label).nextElementSibling?.textContent;
    expect(valueOf(ASKED)).toBe("4");
    expect(valueOf(APPLIED)).toBe("3");
    expect(valueOf(NOT_APPLIED)).toBe("2");
    expect(valueOf(UNSCORED)).toBe("1");
  });

  it("renders no figures block and no next step when given neither", () => {
    render(<AiResultCard tone="success" outcome="X" />);
    expect(screen.getByTestId("ai-result-card").textContent).toBe("X");
  });

  it("refuses not-applied reasons that do not add up", () => {
    expect(() =>
      render(
        <AiResultCard
          tone="warning"
          outcome="X"
          figures={{
            ...FIGURES,
            notAppliedReasons: [{ reason: "R", count: 25 }],
          }}
        />,
      ),
    ).toThrow(/add up to 25, not 27/);
  });

  it.each(["asked", "applied", "notApplied", "unscored"] as const)(
    "refuses a %s count that is not a whole number from zero",
    (key) => {
      for (const value of [-1, 1.5, Number.NaN]) {
        expect(() =>
          render(
            <AiResultCard
              tone="warning"
              outcome="X"
              figures={{
                ...FIGURES,
                notAppliedReasons: undefined,
                [key]: value,
              }}
            />,
          ),
        ).toThrow(/not a whole number from zero/);
      }
    },
  );

  it("refuses a reason count that is not a whole number", () => {
    expect(() =>
      render(
        <AiResultCard
          tone="warning"
          outcome="X"
          figures={{
            ...FIGURES,
            notApplied: 1,
            notAppliedReasons: [
              { reason: "A", count: 1.5 },
              { reason: "B", count: -0.5 },
            ],
          }}
        />,
      ),
    ).toThrow(/has a count that is not a whole number/);
  });
});

describe("AiResultCard refuses what it cannot render honestly (for #1087)", () => {
  it("refuses an unknown tone rather than a class ending in undefined", () => {
    expect(() =>
      render(<AiResultCard tone={"pending" as never} outcome="X" />),
    ).toThrow(/unknown tone "pending"/);
  });

  it("refuses a blank reason", () => {
    expect(() =>
      render(
        <AiResultCard
          tone="success"
          outcome="X"
          figures={{
            ...FIGURES,
            notApplied: 1,
            notAppliedReasons: [{ reason: " ", count: 1 }],
          }}
        />,
      ),
    ).toThrow(/blank reason under "Not applied"/);
  });

  it.each([[""], [null], [[]]])(
    "refuses empty next-step content %j under the fixed label",
    (content) => {
      expect(() =>
        render(
          <AiResultCard
            tone="success"
            outcome="X"
            nextStep={content as never}
          />,
        ),
      ).toThrow(/empty next-step content/);
    },
  );
});
