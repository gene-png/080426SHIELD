import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ZtDroppedSuggestion, ZtRunAiResponse } from "@/lib/zt/types";

import { ZtRunAiAccounting } from "./ZtRunAiAccounting";

// No client mocking needed: this component is pure. That is why it lives in its
// own file — the VALIDATION drop branches are unreachable through a fixture-mode
// run, since the fixture echoes the payload keys back with in-range values, so
// they can only be covered here and in the API unit tests.
//
// `protected` is the exception (round 2): it is fixture-ONLY, because
// `protected_keys` returns an empty set off-fixture. A blanket "fixture mode
// cannot produce a drop" is false for ZT.

function drop(over: Partial<ZtDroppedSuggestion> = {}): ZtDroppedSuggestion {
  return { reason: "unknown_key", key: null, field: null, values: 1, ...over };
}

/**
 * The headline's counts sit inside a `<span>`, so `getByText` cannot match the
 * sentence across the element boundary — read the paragraph's textContent,
 * which is also what a screen reader announces.
 */
function headline(container: HTMLElement): string {
  return container.querySelector("p")?.textContent ?? "";
}

function result(over: Partial<ZtRunAiResponse> = {}): ZtRunAiResponse {
  return {
    changed: [],
    answers: [],
    suggestions_received: 0,
    suggestions_applied: 0,
    dropped: [],
    ...over,
  };
}

describe("ZtRunAiAccounting (W1, issue #44)", () => {
  it("states the accounting on a CLEAN run, so its absence never means zero", () => {
    const { container } = render(
      <ZtRunAiAccounting
        result={result({ suggestions_received: 12, suggestions_applied: 12 })}
      />,
    );
    expect(headline(container)).toMatch(/AI applied 12 of 12 suggested values/);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("refuses to call a zero-suggestion run clean", () => {
    render(<ZtRunAiAccounting result={result()} />);
    expect(screen.getByRole("alert")).toHaveTextContent(
      /returned no suggestions at all/,
    );
    expect(screen.queryByText(/AI applied/)).toBeNull();
  });

  it("itemizes a rejected suggestion with the code the model wrote", () => {
    render(
      <ZtRunAiAccounting
        result={result({
          suggestions_received: 1,
          suggestions_applied: 0,
          dropped: [drop({ reason: "unknown_key", key: "NOPE-1" })],
        })}
      />,
    );
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("NOPE-1");
    expect(alert).toHaveTextContent(/no matching capability/);
  });

  it("counts VALUES, not records, in the failure headline", () => {
    render(
      <ZtRunAiAccounting
        result={result({
          suggestions_received: 2,
          suggestions_applied: 0,
          dropped: [drop({ reason: "entry_shape", values: 2 })],
        })}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "2 suggested values could not be applied",
    );
  });

  it("shows what the model actually sent, not just that it was rejected", () => {
    render(
      <ZtRunAiAccounting
        result={result({
          suggestions_received: 1,
          suggestions_applied: 0,
          dropped: [
            drop({
              reason: "out_of_range",
              key: "ID-1",
              field: "current",
              value: "9",
            }),
          ],
        })}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("ID-1 current = 9");
  });

  it("shows an unrecognized field WITHOUT crying failure", () => {
    render(
      <ZtRunAiAccounting
        result={result({
          suggestions_received: 2,
          suggestions_applied: 1,
          dropped: [
            drop({
              reason: "unknown_field",
              key: "ID-1",
              field: "maturity_level",
            }),
          ],
        })}
      />,
    );
    expect(screen.getByText(/does not recognize/)).toBeInTheDocument();
    expect(screen.getByText(/maturity_level/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("says the unrecognized values are the shortfall, not extra detail", () => {
    render(
      <ZtRunAiAccounting
        result={result({
          suggestions_received: 2,
          suggestions_applied: 1,
          dropped: [drop({ reason: "unknown_field", field: "confidence" })],
        })}
      />,
    );
    expect(
      screen.getByText(/part of the shortfall in the line above/),
    ).toBeInTheDocument();
    expect(screen.getByText(/not extra/)).toBeInTheDocument();
  });

  it("reports a wrapper key as the many values it hides", () => {
    render(
      <ZtRunAiAccounting
        result={result({
          suggestions_received: 5,
          suggestions_applied: 0,
          dropped: [
            drop({
              reason: "unknown_field",
              key: "ID-1",
              field: "stages",
              values: 5,
            }),
          ],
        })}
      />,
    );
    expect(screen.getByText(/5 values came back/)).toBeInTheDocument();
    expect(screen.getByRole("listitem")).toHaveTextContent(
      "ID-1 stages (5 values)",
    );
  });

  it("keeps locked and protected OUT of the failure alert, and apart from each other", () => {
    // The whole point of `protected` being its own reason: telling a consultant
    // a row is "locked" when nobody locked it is a false statement about who
    // decided. Both are by-design skips, so neither may raise an alert.
    render(
      <ZtRunAiAccounting
        result={result({
          suggestions_received: 6,
          suggestions_applied: 2,
          dropped: [
            drop({ reason: "locked", key: "ID-1", values: 2 }),
            drop({ reason: "protected", key: "ID-2", values: 2 }),
          ],
        })}
      />,
    );
    expect(screen.queryByRole("alert")).toBeNull();
    const items = screen.getAllByRole("listitem").map((li) => li.textContent);
    expect(
      items.some((t) => /2 suggested values skipped.*locked/.test(t ?? "")),
    ).toBe(true);
    expect(
      items.some((t) =>
        /2 suggested values skipped.*not written by the AI/.test(t ?? ""),
      ),
    ).toBe(true);
  });

  it("never says '0 suggested values skipped'", () => {
    // Reachable in live mode: field-name drift on a locked row gives the
    // `locked` record `values: 0`, because its values are counted under the
    // drifted names they arrived with. "0 skipped" reads as a contradiction,
    // exactly as it did in the failure block. Fixture mode cannot produce it,
    // which is why only an adversarial read found it.
    render(
      <ZtRunAiAccounting
        result={result({
          suggestions_received: 1,
          suggestions_applied: 0,
          dropped: [
            drop({ reason: "unknown_field", key: "ID-1", field: "stage" }),
            drop({ reason: "locked", key: "ID-1", values: 0 }),
          ],
        })}
      />,
    );
    const skipped = screen
      .getAllByRole("listitem")
      .map((li) => li.textContent ?? "")
      .filter((t) => /skipped/.test(t));
    expect(skipped).toHaveLength(1);
    expect(skipped[0]).not.toMatch(/0 suggested value/);
    expect(skipped[0]).toMatch(/Suggestions skipped .* row is locked/);
  });

  it("shows an unmapped reason code instead of an empty bullet", () => {
    render(
      <ZtRunAiAccounting
        result={result({
          suggestions_received: 1,
          suggestions_applied: 0,
          dropped: [
            drop({
              reason: "invented_later" as ZtDroppedSuggestion["reason"],
            }),
          ],
        })}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("invented_later");
  });

  it("names the row fault even when it accounts for no values of its own", () => {
    // A `values: 0` unknown_key beside an unknown_field is the shape that made
    // the CSF panel print "0 suggested values could not be applied" over a red
    // alert — a contradiction that invites dismissing the alert.
    render(
      <ZtRunAiAccounting
        result={result({
          suggestions_received: 5,
          suggestions_applied: 0,
          dropped: [
            drop({
              reason: "unknown_field",
              key: "ZZ-9",
              field: "x",
              values: 5,
            }),
            drop({ reason: "unknown_key", key: "ZZ-9", values: 0 }),
          ],
        })}
      />,
    );
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(/no matching capability/);
    expect(alert).toHaveTextContent("ZZ-9");
    expect(alert).toHaveTextContent(/Some suggestions could not be applied/);
    expect(alert).not.toHaveTextContent("0 suggested value");
    expect(screen.getByText(/5 values came back/)).toBeInTheDocument();
  });

  it("caps a systematic drift instead of printing a wall of bullets", () => {
    render(
      <ZtRunAiAccounting
        result={result({
          suggestions_received: 25,
          suggestions_applied: 0,
          dropped: Array.from({ length: 25 }, (_, i) =>
            drop({ reason: "unknown_field", key: `ID-${i}`, field: "conf" }),
          ),
        })}
      />,
    );
    expect(screen.getByText(/25 values came back/)).toBeInTheDocument();
    // 10 shown + one overflow line.
    expect(screen.getAllByRole("listitem")).toHaveLength(11);
    expect(screen.getByText("and 15 more records")).toBeInTheDocument();
  });

  it("renders all three buckets at once and they reconcile with the headline", () => {
    const { container } = render(
      <ZtRunAiAccounting
        result={result({
          suggestions_received: 10,
          suggestions_applied: 3,
          dropped: [
            drop({ reason: "out_of_range", key: "ID-1", field: "current" }),
            drop({
              reason: "unknown_field",
              key: "ID-2",
              field: "x",
              values: 4,
            }),
            drop({ reason: "locked", key: "ID-3", values: 2 }),
          ],
        })}
      />,
    );
    expect(headline(container)).toMatch(/AI applied 3 of 10 suggested values/);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "1 suggested value could not be applied",
    );
    expect(screen.getByText(/4 values came back/)).toBeInTheDocument();
    expect(
      screen
        .getAllByRole("listitem")
        .some((li) => /2 suggested values skipped/.test(li.textContent ?? "")),
    ).toBe(true);
  });
});
