import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

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
