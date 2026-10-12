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

describe("AiResultCard figures and next step (rule 8, for #1087)", () => {
  const FIGURES = [
    { label: "L-ASKED", value: 45 },
    { label: "L-APPLIED", value: 18 },
    {
      label: "L-NOT-APPLIED",
      value: 27,
      reasons: [
        { reason: "R-NO-NOTES", count: 25 },
        { reason: "R-OUT-OF-RANGE", count: 2 },
      ],
    },
    { label: "L-UNSCORED", value: 0 },
  ];

  it("renders outcome, then the figures in the caller's order, then detail, then the next step", () => {
    render(
      <AiResultCard
        tone="warning"
        outcome="OUTCOME"
        figures={FIGURES}
        nextStep={{ label: "L-NEXT", content: "NEXT-CONTENT" }}
      >
        <p>DETAIL</p>
      </AiResultCard>,
    );
    const card = screen.getByTestId("ai-result-card");
    expect(card.textContent).toBe(
      "OUTCOME" +
        "L-ASKED45" +
        "L-APPLIED18" +
        "L-NOT-APPLIED27R-NO-NOTES 25R-OUT-OF-RANGE 2" +
        "L-UNSCORED0" +
        "DETAIL" +
        "L-NEXTNEXT-CONTENT",
    );
    const terms = screen
      .getByTestId("ai-result-figures")
      .querySelectorAll("dt");
    expect([...terms].map((t) => t.textContent)).toEqual([
      "L-ASKED",
      "L-APPLIED",
      "L-NOT-APPLIED",
      "L-UNSCORED",
    ]);
  });

  it("ships no fixed figure or next-step label of its own", () => {
    render(
      <AiResultCard
        tone="success"
        outcome="X"
        figures={[{ label: "L", value: 1 }]}
        nextStep={{ label: "N", content: "C" }}
      />,
    );
    expect(screen.getByTestId("ai-result-card").textContent).toBe("XL1NC");
  });

  it("refuses reasons that do not add up to their figure", () => {
    expect(() =>
      render(
        <AiResultCard
          tone="warning"
          outcome="X"
          figures={[
            {
              label: "L-NOT-APPLIED",
              value: 27,
              reasons: [{ reason: "R", count: 25 }],
            },
          ]}
        />,
      ),
    ).toThrow(/add up to 25, not 27/);
  });

  it.each([-1, 1.5, Number.NaN])("refuses a figure of %s", (value) => {
    expect(() =>
      render(
        <AiResultCard
          tone="warning"
          outcome="X"
          figures={[{ label: "L", value }]}
        />,
      ),
    ).toThrow(/not a whole number from zero/);
  });

  it("refuses a reason count that is not a whole number", () => {
    expect(() =>
      render(
        <AiResultCard
          tone="warning"
          outcome="X"
          figures={[
            {
              label: "L",
              value: 1,
              reasons: [
                { reason: "A", count: 1.5 },
                { reason: "B", count: -0.5 },
              ],
            },
          ]}
        />,
      ),
    ).toThrow(/has a count that is not a whole number/);
  });
});
