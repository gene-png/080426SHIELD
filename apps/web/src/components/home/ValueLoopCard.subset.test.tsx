import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ValueLoopCard, type ValueSummary } from "./ValueLoopCard";

/**
 * #889 (Q3): the home card's ATT&CK total sums Gap over the same rows the
 * dashboard reads. A row crediting a tool outside the client's current
 * security tool list may read Covered instead of Gap, so the total may be
 * understated, and the card says so. Copy C7 as reworded on review F1,
 * written out.
 */

const C7 =
  "Some techniques counted as covered rely on a tool that is not in the client's current security tool list, so this total may be understated.";

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

describe("ValueLoopCard, tools outside the security tool list (#889)", () => {
  it("says the total may be understated", () => {
    render(
      <ValueLoopCard
        summary={summary({ attack_counts_outside_subset: true })}
      />,
    );
    expect(screen.getByText("3 techniques uncovered")).toBeInTheDocument();
    expect(
      screen.getByText(new RegExp(C7.replace(/[.]/g, "[.]"))),
    ).toBeInTheDocument();
  });

  it.each([false, null, undefined])(
    "says nothing when the flag is %s",
    (flag) => {
      render(
        <ValueLoopCard
          summary={summary({ attack_counts_outside_subset: flag })}
        />,
      );
      // APPEAR before ABSENT.
      expect(screen.getByText("3 techniques uncovered")).toBeInTheDocument();
      expect(screen.queryByText(/security tool list/)).toBeNull();
    },
  );
});
