import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("names the four ordinary states", () => {
    render(<StatusBadge status="covered" />);
    expect(screen.getByText("Covered")).toBeInTheDocument();
  });

  it("says pending review, and does NOT say Covered on its own", () => {
    // 5.1: a technique whose support is unconfirmed gets its OWN visible state.
    // The matrix badge is where a consultant reads a single technique, and a
    // green "Covered" cell over a row the rollup is withholding is the two
    // surfaces of the same product disagreeing about the same technique.
    render(<StatusBadge status="covered" pendingReview />);
    expect(screen.getByText(/Pending review/)).toBeInTheDocument();
    expect(screen.queryByText("Covered")).toBeNull();
  });

  it("still shows WHICH status is being withheld", () => {
    // Not collapsed into a bare "pending". The stored status survives underneath
    // — clearing the citation puts the technique back into it — so the badge
    // says what it will become, which is also what stops `pending` reading as a
    // fifth status rather than a held claim.
    render(<StatusBadge status="partial" pendingReview />);
    expect(screen.getByText(/Pending review/)).toHaveTextContent(/partial/i);
  });

  it("is not the gap badge", () => {
    // The one collapse 5.1 explicitly rejected: gap says nothing was found,
    // pending says something was found and is not confirmed. Asserted on the
    // rendered class, because "it looks like a gap" is how a consultant would
    // actually be misled — the word alone could differ while the colour does not.
    const { container: pending } = render(
      <StatusBadge status="covered" pendingReview />,
    );
    const { container: gap } = render(<StatusBadge status="gap" />);
    const cls = (c: HTMLElement) => c.querySelector("span")?.className ?? "";
    expect(cls(pending)).not.toEqual(cls(gap));
    expect(cls(pending)).not.toMatch(/status-danger/);
  });

  it("ignores pendingReview on an unscored row", () => {
    // There is no claim to withhold, and the backend never marks one — a badge
    // that could show "pending" over a row nobody assessed would be inventing a
    // state the score does not have.
    render(<StatusBadge status={null} pendingReview />);
    expect(screen.getByText("Unscored")).toBeInTheDocument();
    expect(screen.queryByText(/Pending review/)).toBeNull();
  });
});
