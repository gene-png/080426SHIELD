import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Fragment } from "react";
import type * as React from "react";

import { AiResultCard } from "./AiResultCard";

// Figures are required (round 6 review, F1): every card shows its counts, and
// all zeros is a valid run. Tests about something else pass these.
const ZERO = { asked: 0, applied: 0, notApplied: 0, unscored: 0 };
const ZERO_TEXT = "Asked0Applied0Not applied0Unscored0";

describe("AiResultCard (for #1087)", () => {
  it("leads with the outcome: the card's text starts with it", () => {
    render(
      <AiResultCard
        tone="warning"
        outcome="40 of 45 rows scored"
        figures={ZERO}
      >
        <p>DETAIL</p>
      </AiResultCard>,
    );
    const card = screen.getByTestId("ai-result-card");
    expect(card.textContent?.startsWith("40 of 45 rows scored")).toBe(true);
    expect(card.textContent).toBe(`40 of 45 rows scored${ZERO_TEXT}DETAIL`);
  });

  it("puts the outcome before the detail in the document", () => {
    render(
      <AiResultCard tone="success" outcome="OUTCOME" figures={ZERO}>
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
      render(<AiResultCard tone={tone} outcome="X" figures={ZERO} />);
      const card = screen.getByTestId("ai-result-card");
      expect(card.textContent).toBe(`X${ZERO_TEXT}`);
      expect(card.className).toContain(`bg-${own}-bg`);
      for (const other of others) expect(card.className).not.toContain(other);
    },
  );

  it.each(["", "   "])("refuses a blank outcome %j", (outcome) => {
    expect(() =>
      render(<AiResultCard tone="success" outcome={outcome} figures={ZERO} />),
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
        figures={{
          asked: 6,
          applied: 3,
          notApplied: 2,
          notAppliedReasons: [{ reason: "R", count: 2 }],
          unscored: 1,
        }}
      />,
    );
    const valueOf = (label: string) =>
      screen.getByText(label).nextElementSibling?.textContent;
    expect(valueOf(ASKED)).toBe("6");
    expect(valueOf(APPLIED)).toBe("3");
    expect(valueOf(NOT_APPLIED)).toBe("2R 2");
    expect(valueOf(UNSCORED)).toBe("1");
  });

  // Was "renders no figures block and no next step when given neither": F1
  // makes figures required, so only the next-step half still holds.
  it("renders no next step when given none", () => {
    render(<AiResultCard tone="success" outcome="X" figures={ZERO} />);
    expect(screen.getByTestId("ai-result-card").textContent).toBe(
      `X${ZERO_TEXT}`,
    );
    expect(screen.queryByTestId("ai-result-next")).toBeNull();
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
      render(
        <AiResultCard tone={"pending" as never} outcome="X" figures={ZERO} />,
      ),
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
            figures={ZERO}
            nextStep={content as never}
          />,
        ),
      ).toThrow(/empty next-step content/);
    },
  );
});

// Fragments: Children.toArray does not look inside them, so these are the
// rows a toArray-only check would let through (round 4 review).
const EMPTY_FRAGMENTS: [string, React.ReactNode][] = [
  ["<></>", <></>],
  ["<>{null}</>", <>{null}</>],
  [
    '<><>{false}</><>{""}</></>',
    <>
      <>{false}</>
      <>{""}</>
    </>,
  ],
  ['<Fragment key="k">{null}</Fragment>', <Fragment key="k">{null}</Fragment>],
  ['<>{[null, ""]}</>', <>{[null, ""]}</>],
];

// Content that must be ACCEPTED: only Fragments are looked inside. Any other
// element counts as content, even one that renders nothing (round 5 review:
// widening the recursion to every element would throw on these).
function RendersNothing(): null {
  return null;
}
const REAL_CONTENT: [string, React.ReactNode][] = [
  ["<div>{null}</div>", <div key="d">{null}</div>],
  ["<RendersNothing />, a component element", <RendersNothing key="c" />],
  ['<Fragment key="k">REAL</Fragment>', <Fragment key="k">REAL</Fragment>],
  ['<>{[null, <p key="a">REAL</p>]}</>', <>{[null, <p key="a">REAL</p>]}</>],
];

describe("AiResultCard next step looks inside fragments (for #1087)", () => {
  it.each(EMPTY_FRAGMENTS)("refuses next step %s", (_name, nextStep) => {
    expect(() =>
      render(
        <AiResultCard
          tone="success"
          outcome="X"
          figures={ZERO}
          nextStep={nextStep}
        />,
      ),
    ).toThrow(/empty next-step content/);
  });

  it("accepts a fragment with real content", () => {
    render(
      <AiResultCard
        tone="success"
        outcome="X"
        figures={ZERO}
        nextStep={
          <>
            <>{null}</>
            <>NEXT</>
          </>
        }
      />,
    );
    expect(screen.getByTestId("ai-result-next").textContent).toBe(
      "What to do nextNEXT",
    );
  });
});

const R2 = [{ reason: "R", count: 2 }];

describe("AiResultCard figures partition what was asked (ruling, for #1087)", () => {
  it.each([
    [
      {
        asked: 7,
        applied: 3,
        notApplied: 2,
        notAppliedReasons: R2,
        unscored: 1,
      },
      "6",
    ],
    [
      {
        asked: 5,
        applied: 3,
        notApplied: 2,
        notAppliedReasons: R2,
        unscored: 1,
      },
      "6",
    ],
  ])("refuses %j: the parts add up to %s", (figures, parts) => {
    expect(() =>
      render(<AiResultCard tone="warning" outcome="X" figures={figures} />),
    ).toThrow(
      new RegExp(
        `Applied, Not applied and Unscored add up to ${parts}, not Asked ${figures.asked}`,
      ),
    );
  });

  it("accepts all zeros", () => {
    render(
      <AiResultCard
        tone="success"
        outcome="X"
        figures={{ asked: 0, applied: 0, notApplied: 0, unscored: 0 }}
      />,
    );
    expect(screen.getByTestId("ai-result-figures")).toBeInTheDocument();
  });
});

describe("AiResultCard next step looks inside Fragments only (for #1087)", () => {
  it.each(REAL_CONTENT)("accepts next step %s", (_name, nextStep) => {
    render(
      <AiResultCard
        tone="success"
        outcome="X"
        figures={ZERO}
        nextStep={nextStep}
      />,
    );
    expect(screen.getByTestId("ai-result-next")).toBeInTheDocument();
  });
});

describe("AiResultCard's outcome on a missing value (for #1087)", () => {
  it.each([[null], [undefined]])(
    "refuses outcome %s by name, not with a TypeError",
    (outcome) => {
      expect(() =>
        render(
          <AiResultCard
            tone="success"
            outcome={outcome as never}
            figures={ZERO}
          />,
        ),
      ).toThrow(/a blank outcome/);
    },
  );
});

// Round 6 review, F1: a card with no counts, or a "Not applied" figure with no
// reasons, reads as a full account while giving none (rule 7: exclusions sit
// beside the figure and account for all of it).
describe("AiResultCard requires its figures and their reasons (F1, for #1087)", () => {
  it("refuses a card with no figures", () => {
    expect(() =>
      // @ts-expect-error -- figures is required; this pins the type as well.
      render(<AiResultCard tone="success" outcome="X" />),
    ).toThrow(/AiResultCard: no figures/);
  });

  it("refuses a Not applied count above zero with no reasons", () => {
    expect(() =>
      render(
        <AiResultCard
          tone="warning"
          outcome="X"
          figures={{ asked: 45, applied: 18, notApplied: 27, unscored: 0 }}
        />,
      ),
    ).toThrow(/"Not applied" is 27 but no reasons were given/);
  });

  it("refuses an empty reasons list under a Not applied count above zero", () => {
    expect(() =>
      render(
        <AiResultCard
          tone="warning"
          outcome="X"
          figures={{ ...FIGURES, notAppliedReasons: [] }}
        />,
      ),
    ).toThrow(/add up to 0, not 27/);
  });

  it("accepts no reasons when Not applied is zero", () => {
    render(
      <AiResultCard
        tone="success"
        outcome="X"
        figures={{ asked: 3, applied: 3, notApplied: 0, unscored: 0 }}
      />,
    );
    expect(screen.getByText(NOT_APPLIED).nextElementSibling?.textContent).toBe(
      "0",
    );
  });

  it.each([
    ["the same reason twice", "R-NO-NOTES", "R-NO-NOTES"],
    ["reasons equal once trimmed", "R-NO-NOTES", " R-NO-NOTES "],
  ])("refuses %s", (_name, first, second) => {
    expect(() =>
      render(
        <AiResultCard
          tone="warning"
          outcome="X"
          figures={{
            ...FIGURES,
            notAppliedReasons: [
              { reason: first, count: 25 },
              { reason: second, count: 2 },
            ],
          }}
        />,
      ),
    ).toThrow(/duplicate reason "R-NO-NOTES" under "Not applied"/);
  });
});
