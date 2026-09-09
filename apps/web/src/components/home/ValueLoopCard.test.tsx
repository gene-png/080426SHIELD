import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ValueLoopCard, type ValueSummary } from "./ValueLoopCard";

/**
 * #114 review: a null slot was carrying two different facts.
 *
 * "This service has not released a report yet" and "this service HAS released a
 * report and we cannot match this figure to it" both rendered as **Pending**.
 * The second is a false negative told to a client who is holding the report,
 * and the alternative the endpoint used to take — refusing the whole response —
 * removed the client's home page, because `/home` fetches `/value-summary` in an
 * unguarded `Promise.all` and there is no error boundary under `app/`.
 *
 * These tests pin the three states apart at the RENDER, which is the only place
 * the distinction is worth anything: the API has carried enough information to
 * tell them apart before and no surface read it.
 */

/** A summary with everything pending and nothing unresolved. Overridden per test. */
function summary(over: Partial<ValueSummary> = {}): ValueSummary {
  return {
    tech_debt_savings_usd: null,
    tech_debt_savings_cost_known: true,
    tech_debt_savings_unresolved: false,
    zt_gap_count: null,
    zt_gap_unresolved: false,
    attack_uncovered_count: null,
    attack_uncovered_unresolved: false,
    csf_gap_count: null,
    csf_gap_unresolved: false,
    has_any_data: false,
    has_unresolved: false,
    ...over,
  };
}

describe("ValueLoopCard", () => {
  it("renders nothing for a brand-new client with no data and nothing unresolved", () => {
    const { container } = render(<ValueLoopCard summary={summary()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("stays on the page when every figure is unresolvable and none is resolvable", () => {
    // The case that used to disappear in silence: `has_any_data` is false, so a
    // guard reading only that renders null — no card, no message, no gap.
    render(
      <ValueLoopCard
        summary={summary({
          has_unresolved: true,
          csf_gap_unresolved: true,
          zt_gap_unresolved: true,
          attack_uncovered_unresolved: true,
          tech_debt_savings_unresolved: true,
        })}
      />,
    );
    expect(screen.getByText("Your engagement at a glance")).toBeInTheDocument();
    expect(screen.getAllByText("Not available")).toHaveLength(4);
  });

  it("distinguishes unresolved from pending, and does not say Pending for either wrongly", () => {
    // The discriminating test. Both slots are null; only the flag separates
    // them, so an implementation that ignores the flag fails here and nowhere
    // else. Asserting the ABSENT branch too: proving "Not available" renders
    // says nothing about whether "Pending" wrongly renders beside it.
    render(
      <ValueLoopCard
        summary={summary({
          csf_gap_unresolved: true,
          has_unresolved: true,
          zt_gap_count: 4,
          has_any_data: true,
        })}
      />,
    );

    expect(screen.getByText("Not available")).toBeInTheDocument();
    expect(screen.getByText("4 gaps to close")).toBeInTheDocument();
    // ATT&CK and Tech debt are genuinely pending — two of them, and exactly two.
    expect(screen.getAllByText("Pending")).toHaveLength(2);
    expect(
      screen.getByText(/can't be matched to it, so we're not showing a number/),
    ).toBeInTheDocument();
  });

  it("tells an unresolved client their report is still reachable", () => {
    // The copy is the whole point of choosing null over raise: the client keeps
    // the page, keeps the report, and is told which figure is missing and why.
    render(
      <ValueLoopCard
        summary={summary({ zt_gap_unresolved: true, has_unresolved: true })}
      />,
    );
    expect(
      screen.getByText(/released and available under Results/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Ask your analyst to confirm it/),
    ).toBeInTheDocument();
  });

  it("still renders a resolved figure with no unresolved noise", () => {
    render(
      <ValueLoopCard
        summary={summary({ csf_gap_count: 7, has_any_data: true })}
      />,
    );
    expect(screen.getByText("7 gaps to close")).toBeInTheDocument();
    expect(screen.queryByText("Not available")).not.toBeInTheDocument();
  });
});
