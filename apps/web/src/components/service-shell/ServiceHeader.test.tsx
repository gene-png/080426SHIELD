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

  it("shows the caller's version, status and stage, each as written, with no label of its own (rule 5)", () => {
    renderHeader();
    expect(screen.getByTestId("service-header-version").textContent).toBe(
      "VERSION-TEXT",
    );
    expect(screen.getByTestId("service-header-status").textContent).toBe(
      "STATUS-TEXT",
    );
    expect(screen.getByTestId("service-header-stage").textContent).toBe(
      "STAGE-TEXT",
    );
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
