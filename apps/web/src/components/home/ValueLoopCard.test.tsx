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
    // No released ZT service, so there is no target to attribute. `null` for
    // both counts is what the API sends whenever the figure is null — see
    // `_TargetedKindTotal`. A fixture setting `0` here would assert "nothing
    // was assumed" about a figure that does not exist, and would put the test
    // suite in a state the server never produces.
    zt_services: 0,
    zt_targets_defaulted: null,
    zt_targets_unusable: null,
    attack_uncovered_count: null,
    attack_uncovered_unresolved: false,
    csf_gap_count: null,
    csf_gap_unresolved: false,
    csf_services: 0,
    csf_targets_defaulted: null,
    csf_targets_unusable: null,
    has_any_data: false,
    has_unresolved: false,
    ...over,
  };
}

/** A resolved ZT figure whose target was entirely the client's own choice. */
function ztChosen(count: number): Partial<ValueSummary> {
  return {
    zt_gap_count: count,
    zt_services: 1,
    zt_targets_defaulted: 0,
    zt_targets_unusable: 0,
    has_any_data: true,
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
    // Names the KIND and says the withholding is wider than one report. The
    // previous copy said "your report for this service", false whenever the
    // client has more than one — and Zero Trust can span two frameworks in one
    // slot, because `zt_ids` concatenates CISA and DoD.
    expect(
      screen.getByText(/can't match this figure to your NIST CSF reports/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/including for any of them that are fine/),
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
      screen.getByText(/still available under Results/),
    ).toBeInTheDocument();
    // NOT "ask your analyst to confirm it". The analyst's only in-product move
    // is to re-release, and `deliverable_release.py` and migration 0041 both
    // claim that repairs a NULL `parent_version` when it does not —
    // `_release_parent` returns at the NULL check (#59). Routing a client to a
    // remedy the tree records as a no-op is the defect, not the wording.
    expect(screen.queryByText(/confirm it/)).not.toBeInTheDocument();
    expect(
      screen.getByText(/analyst will need to look into it/),
    ).toBeInTheDocument();
  });

  it("lets the FLAG win over a value, so a number never sits under 'not showing a number'", () => {
    // Finding D, and it is the same defect as the untested flag one level up:
    // the render read `m.value ?? (m.unresolved ? …)`, so a response carrying
    // BOTH printed the figure while the hint below said we were not showing
    // one. No backend path produces that pair today — but that is a guarantee
    // held in another file, and this pins the renderer instead of trusting it.
    render(
      <ValueLoopCard
        summary={summary({
          csf_gap_count: 7,
          csf_gap_unresolved: true,
          has_any_data: true,
          has_unresolved: true,
        })}
      />,
    );
    expect(screen.getByText("Not available")).toBeInTheDocument();
    expect(screen.queryByText("7 gaps to close")).not.toBeInTheDocument();
  });

  it("still renders a resolved figure with no unresolved noise", () => {
    render(
      <ValueLoopCard
        summary={summary({
          csf_gap_count: 7,
          csf_services: 1,
          csf_targets_defaulted: 0,
          csf_targets_unusable: 0,
          has_any_data: true,
        })}
      />,
    );
    expect(screen.getByText("7 gaps to close")).toBeInTheDocument();
    expect(screen.queryByText("Not available")).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // #207 — the target the figure was counted against.
  // -------------------------------------------------------------------------

  it("says YOUR target only when the client chose every one of them", () => {
    render(<ValueLoopCard summary={summary(ztChosen(4))} />);
    expect(
      screen.getByText("Capabilities below your target maturity stage."),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("value-target-note")).not.toBeInTheDocument();
  });

  it("drops the possessive AND discloses the count when a target was assumed", () => {
    // Both halves, because either alone is still wrong: the possessive without
    // the note is the original lie, and the note under "your target maturity
    // stage" contradicts the sentence above it.
    render(
      <ValueLoopCard
        summary={summary({
          ...ztChosen(4),
          zt_services: 3,
          zt_targets_defaulted: 2,
        })}
      />,
    );
    expect(
      screen.getByText("Capabilities below the target maturity stage."),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Capabilities below your target maturity stage."),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("value-target-note")).toHaveTextContent(
      "2 of 3 Zero Trust reports counted against the standard stage — no stage chosen at intake.",
    );
  });

  it("does not tell a client they chose nothing when their choice was discarded", () => {
    render(
      <ValueLoopCard
        summary={summary({
          ...ztChosen(4),
          zt_services: 1,
          zt_targets_unusable: 1,
        })}
      />,
    );
    const note = screen.getByTestId("value-target-note");
    expect(note).toHaveTextContent("the stage on file could not be used");
    expect(note).not.toHaveTextContent(/no stage chosen/);
  });

  it("puts no target note beside a figure it is not showing", () => {
    // The unresolved branch renders no number, so a sentence qualifying one
    // would be attached to nothing. The API sends null counts there, but the
    // renderer guards it itself rather than relying on that.
    render(
      <ValueLoopCard
        summary={summary({
          zt_gap_unresolved: true,
          has_unresolved: true,
          zt_services: 2,
          zt_targets_defaulted: 2,
        })}
      />,
    );
    expect(screen.getByText("Not available")).toBeInTheDocument();
    expect(screen.queryByTestId("value-target-note")).not.toBeInTheDocument();
  });

  it("qualifies the two gap figures independently", () => {
    // Both twins are wired, and one is not satisfying the other's assertion.
    // `getAllByTestId` would pass over a card that rendered the ZT note twice.
    render(
      <ValueLoopCard
        summary={summary({
          ...ztChosen(4),
          csf_gap_count: 7,
          csf_services: 2,
          csf_targets_defaulted: 0,
          csf_targets_unusable: 2,
        })}
      />,
    );
    const notes = screen.getAllByTestId("value-target-note");
    expect(notes).toHaveLength(1);
    expect(notes[0]).toHaveTextContent(
      "Counted against the standard tier — the tier on file could not be used.",
    );
    expect(
      screen.getByText("Capabilities below your target maturity stage."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Subcategories below the target maturity tier."),
    ).toBeInTheDocument();
  });
});
