import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ValueLoopCard, type ValueSummary } from "./ValueLoopCard";

/**
 * #1011: the home card read "not checked" the same as "checked, none found".
 * The API now says WHY nothing was checked (`attack_subset_not_checked_reason`,
 * present only beside a figure whose tools were not checked), and the card
 * states it. Copy strings 1 to 3 as approved by the advisor (#736 comment
 * 6094262391, on the plan at 6093958175), written out rather than imported.
 */

const NO_LIST =
  "Tools credited for techniques counted as covered were not checked against a security tool list, because the client has none.";
const EMPTY =
  "Tools credited for techniques counted as covered were not checked against a security tool list, because the client's security tool list has no security tools.";
const FALLBACK =
  "Tools credited for techniques counted as covered were not checked against a security tool list.";

function summary(over: Partial<ValueSummary> = {}): ValueSummary {
  return {
    tech_debt_savings_usd: null,
    tech_debt_savings_cost_known: true,
    tech_debt_savings_unresolved: false,
    zt_gap_count: null,
    zt_gap_unresolved: false,
    zt_services: 0,
    zt_targets_defaulted: null,
    zt_targets_unusable: null,
    zt_targets_computed_live: null,
    attack_uncovered_count: 3,
    attack_uncovered_unresolved: false,
    attack_uncovered_withheld: false,
    attack_not_verified_count: null,
    attack_covered_relies_on_outside_tool: null,
    attack_subset_not_checked_reason: null,
    csf_gap_count: null,
    csf_gap_unresolved: false,
    csf_services: 0,
    csf_targets_defaulted: null,
    csf_targets_unusable: null,
    csf_targets_computed_live: null,
    has_any_data: true,
    has_unresolved: false,
    ...over,
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ValueLoopCard, an ATT&CK figure whose tools were not checked (#1011)", () => {
  it.each([
    ["no_list", NO_LIST],
    ["discarded", NO_LIST],
    ["empty", EMPTY],
  ])("states the reason %s in its own words", (reason, sentence) => {
    render(
      <ValueLoopCard
        summary={summary({ attack_subset_not_checked_reason: reason })}
      />,
    );
    // APPEAR before ABSENT.
    expect(screen.getByText("3 techniques uncovered")).toBeInTheDocument();
    const line = screen.getByText(sentence);
    expect(line).toBeInTheDocument();
    // Neutral, not a warning: unchecked is unknown, not found.
    expect(line).toHaveClass("text-ink-tertiary");
    expect(line).not.toHaveClass("text-status-warning-fg");
    // Exactly one of the three, and not the understated note (C7).
    expect(screen.getAllByText(/were not checked against/)).toHaveLength(1);
    expect(screen.queryByText(/may be understated/)).toBeNull();
  });

  it("falls back to the plain sentence for a reason it does not know, logs an error, and still renders", () => {
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <ValueLoopCard
        summary={summary({
          attack_subset_not_checked_reason: "from_a_newer_api",
        })}
      />,
    );
    expect(screen.getByText("3 techniques uncovered")).toBeInTheDocument();
    expect(screen.getByText(FALLBACK)).toBeInTheDocument();
    expect(screen.queryByText(NO_LIST)).toBeNull();
    expect(screen.queryByText(EMPTY)).toBeNull();
    expect(err).toHaveBeenCalledWith(
      "[home] unknown ATT&CK not-checked reason",
      "from_a_newer_api",
    );
  });

  it("does not log for a known reason", () => {
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <ValueLoopCard
        summary={summary({ attack_subset_not_checked_reason: "no_list" })}
      />,
    );
    expect(screen.getByText(NO_LIST)).toBeInTheDocument();
    expect(err).not.toHaveBeenCalled();
  });

  it.each([
    [
      "checked, none found (state B)",
      { attack_covered_relies_on_outside_tool: false },
    ],
    ["no reason sent", {}],
    [
      "an API that predates the field",
      { attack_subset_not_checked_reason: undefined },
    ],
  ])("says nothing for %s", (_label, over: Partial<ValueSummary>) => {
    render(<ValueLoopCard summary={summary(over)} />);
    expect(screen.getByText("3 techniques uncovered")).toBeInTheDocument();
    expect(screen.queryByText(/security tool list/)).toBeNull();
  });

  it("says nothing without a figure (state D)", () => {
    render(
      <ValueLoopCard
        summary={summary({
          attack_uncovered_count: null,
          csf_gap_count: 2,
          attack_subset_not_checked_reason: "no_list",
        })}
      />,
    );
    // The card is up (the CSF figure), and the ATT&CK slot is Pending.
    expect(screen.getByText("2 gaps to close")).toBeInTheDocument();
    expect(screen.getAllByText("Pending").length).toBeGreaterThan(0);
    expect(screen.queryByText(/security tool list/)).toBeNull();
  });

  it("says nothing beside an unresolved figure", () => {
    render(
      <ValueLoopCard
        summary={summary({
          attack_uncovered_count: null,
          attack_uncovered_unresolved: true,
          has_unresolved: true,
          attack_subset_not_checked_reason: "no_list",
        })}
      />,
    );
    expect(screen.getByText("Not available")).toBeInTheDocument();
    expect(screen.queryByText(/security tool list/)).toBeNull();
  });
});
