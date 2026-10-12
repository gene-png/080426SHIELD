import "@testing-library/jest-dom/vitest";

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SectionHeader, type Visibility } from "./SectionHeader";

// Gene's verbatim copy, written out here as the spec. Plan v2 rules 2 and 6
// (#736, issuecomment-6116093149), which supersede v1's "What this page is
// for": "What this section is for, in one plain sentence; What you can do
// here, in one to three short bullets; its visibility state".
const PURPOSE_LABEL = "What this section is for";
const CAN_DO_LABEL = "What you can do here";
const VISIBILITY: Record<Visibility, string> = {
  internal: "Internal only",
  "client-preview": "Client preview",
  released: "Released to client",
};

function renderHeader(
  visibility: Visibility = "internal",
  canDo: string[] = ["DO-ONE", "DO-TWO"],
) {
  return render(
    <SectionHeader
      title="Overview"
      purpose="PURPOSE-TEXT"
      canDo={canDo}
      visibility={visibility}
    />,
  );
}

describe("SectionHeader (for #1087)", () => {
  it("makes the title the page's h1", () => {
    renderHeader();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      /^Overview$/,
    );
  });

  it("pairs Gene's purpose label with the caller's sentence", () => {
    renderHeader();
    const term = screen.getByText(PURPOSE_LABEL);
    expect(term.tagName).toBe("DT");
    expect(term.nextElementSibling?.textContent).toBe("PURPOSE-TEXT");
    expect(screen.queryByText("What this page is for")).toBeNull();
  });

  it("lists what you can do here as bullets, in the caller's order", () => {
    renderHeader("internal", ["DO-ONE", "DO-TWO", "DO-THREE"]);
    const term = screen.getByText(CAN_DO_LABEL);
    expect(term.tagName).toBe("DT");
    const items = within(term.nextElementSibling as HTMLElement).getAllByRole(
      "listitem",
    );
    expect(items.map((li) => li.textContent)).toEqual([
      "DO-ONE",
      "DO-TWO",
      "DO-THREE",
    ]);
  });

  it.each([[[]], [["1", "2", "3", "4"]]])(
    "refuses %j: the plan allows one to three bullets",
    (canDo) => {
      expect(() => renderHeader("internal", canDo)).toThrow(
        /one to three bullets/,
      );
    },
  );

  it.each(Object.entries(VISIBILITY) as [Visibility, string][])(
    "labels visibility %s as %s, and shows no other label",
    (visibility, label) => {
      renderHeader(visibility);
      const badge = screen.getByTestId("section-visibility");
      expect(badge.textContent).toBe(label);
      for (const other of Object.values(VISIBILITY)) {
        if (other !== label) expect(screen.queryByText(other)).toBeNull();
      }
    },
  );
});
