import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Fragment } from "react";
import type * as React from "react";

import { InternalOnlyBand } from "./InternalOnlyBand";

// Gene's verbatim band text: #736 issuecomment-6115899349 rule 6, and the
// "internal-only band" of issuecomment-6115981718. Written out as the spec.
const BAND = "KENTRO ADMIN ONLY: never shown to the client";

describe("InternalOnlyBand (for #1087)", () => {
  it("shows Gene's band text verbatim, above the content it marks", () => {
    render(
      <InternalOnlyBand>
        <p>ADMIN CONTENT</p>
      </InternalOnlyBand>,
    );
    const band = screen.getByTestId("internal-only-band");
    expect(band.textContent).toBe(`${BAND}ADMIN CONTENT`);
    const label = screen.getByText(BAND);
    const content = screen.getByText("ADMIN CONTENT");
    expect(
      label.compareDocumentPosition(content) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });
});

describe("InternalOnlyBand with nothing to mark (for #1087)", () => {
  it.each([
    [null],
    [false],
    [undefined],
    [true],
    [[]],
    [0],
    [""],
    ["  "],
    [[null, false, ""]],
  ])(
    "refuses %s children: an empty band claims admin content that is not there",
    (children) => {
      expect(() =>
        render(<InternalOnlyBand>{children as never}</InternalOnlyBand>),
      ).toThrow(/nothing to mark/);
    },
  );
});

describe("InternalOnlyBand content that is really there (for #1087)", () => {
  it.each([
    ["a text node", "ADMIN TEXT"],
    ["a non-zero number", 7],
    ["a list with one real item", [null, <p key="a">ADMIN ITEM</p>]],
  ])("accepts %s", (_name, children) => {
    render(<InternalOnlyBand>{children as never}</InternalOnlyBand>);
    expect(screen.getByTestId("internal-only-band")).toBeInTheDocument();
  });
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

describe("InternalOnlyBand looks inside fragments (for #1087)", () => {
  it.each(EMPTY_FRAGMENTS)("refuses %s", (_name, children) => {
    expect(() =>
      render(<InternalOnlyBand>{children}</InternalOnlyBand>),
    ).toThrow(/nothing to mark/);
  });

  it("accepts a fragment with real content inside a nested fragment", () => {
    render(
      <InternalOnlyBand>
        <>
          <>{null}</>
          <>
            <p>ADMIN ROW</p>
          </>
        </>
      </InternalOnlyBand>,
    );
    expect(screen.getByText("ADMIN ROW")).toBeInTheDocument();
  });
});

describe("InternalOnlyBand looks inside Fragments only (for #1087)", () => {
  it.each(REAL_CONTENT)("accepts %s", (_name, children) => {
    render(<InternalOnlyBand>{children}</InternalOnlyBand>);
    expect(screen.getByTestId("internal-only-band")).toBeInTheDocument();
  });
});
