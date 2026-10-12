import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ServiceHeader } from "./ServiceHeader";

type Props = Parameters<typeof ServiceHeader>[0];

function renderHeader(over: Partial<Props> = {}) {
  return render(
    <ServiceHeader
      serviceTitle="Technical Debt Review"
      overviewHref="/svc/td"
      version="VERSION-TEXT"
      status="STATUS-TEXT"
      stage="STAGE-TEXT"
      next={null}
      {...over}
    />,
  );
}

describe("ServiceHeader (for #1087)", () => {
  it('shows "Next:" followed by a real link the caller names', () => {
    renderHeader({
      next: { text: "Review the AI draft", href: "/svc/td/review" },
    });
    const next = screen.getByTestId("service-header-next");
    // Gene's v2 plan (#736, issuecomment-6115981718): 'showing "Next: …"'.
    expect(next.textContent).toBe("Next: Review the AI draft");
    const link = screen.getByRole("link", { name: "Review the AI draft" });
    expect(link).toHaveAttribute("href", "/svc/td/review");
  });

  it("renders no Next line when there is nothing next (that copy is not approved)", () => {
    const { container } = renderHeader();
    expect(screen.getByText("Technical Debt Review")).toBeInTheDocument();
    expect(screen.queryByTestId("service-header-next")).toBeNull();
    expect(container.textContent).not.toMatch(/Next/);
  });

  it("links the service title to its Overview, and is not a heading", () => {
    renderHeader();
    const title = screen.getByRole("link", { name: "Technical Debt Review" });
    expect(title).toHaveAttribute("href", "/svc/td");
    // The page's single h1 is the section title (SectionHeader).
    expect(screen.queryByRole("heading")).toBeNull();
  });

  it("shows version, status and stage under the approved labels (rule 5)", () => {
    // The advisor's approved labels (#736, issuecomment-6128447366),
    // transcribed literally, never imported from the component.
    renderHeader();
    for (const [testId, label, value] of [
      ["service-header-version", "Version", "VERSION-TEXT"],
      ["service-header-status", "Status", "STATUS-TEXT"],
      ["service-header-stage", "Stage", "STAGE-TEXT"],
    ]) {
      const group = screen.getByTestId(testId);
      expect(group.querySelector("dt")?.textContent).toBe(label);
      expect(group.querySelector("dd")?.textContent).toBe(value);
      expect(group.textContent).toBe(`${label}${value}`);
    }
  });

  it.each(["version", "status", "stage"] as const)(
    "refuses a blank %s",
    (name) => {
      expect(() => renderHeader({ [name]: "  " })).toThrow(
        new RegExp(`blank ${name}`),
      );
    },
  );
});

describe("ServiceHeader refuses blank text it would render (for #1087)", () => {
  it.each([
    [
      "next.text",
      { next: { text: "  ", href: "/svc/td/review" } },
      /blank next\.text/,
    ],
    ["next.href", { next: { text: "Review", href: " " } }, /blank next\.href/],
    ["serviceTitle", { serviceTitle: "" }, /blank serviceTitle/],
    [
      "next.text (null)",
      { next: { text: null, href: "/x" } },
      /a blank next\.text/,
    ],
    ["version (undefined)", { version: undefined }, /a blank version/],
    ["overviewHref", { overviewHref: " " }, /blank overviewHref/],
  ] as const)("refuses a blank %s", (_name, over, message) => {
    expect(() => renderHeader(over as Partial<Props>)).toThrow(message);
  });
});
