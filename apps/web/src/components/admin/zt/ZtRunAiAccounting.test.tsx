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
          // `applied > 0` on purpose: with nothing applied the lead switches to
          // the "Nothing was applied" wording, which would stop this test
          // exercising the values-vs-records count it exists to pin.
          suggestions_received: 5,
          suggestions_applied: 3,
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
      items.some((t) =>
        /2 suggested values across 1 capability skipped.*locked/.test(t ?? ""),
      ),
    ).toBe(true);
    expect(
      items.some((t) =>
        /2 suggested values across 1 capability skipped.*not written by the AI/.test(
          t ?? "",
        ),
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
    expect(skipped[0]).toMatch(
      /Suggestions across 1 capability skipped .* row is locked/,
    );
  });

  it("raises an alert when a run applied NOTHING, whichever bucket it fell in", () => {
    // Total field-name drift routes every record to `NOT_UNDERSTOOD`, which is
    // deliberately quiet. Before round 3 that meant 74 lost stages rendered in
    // calm secondary grey with no alert at all — while "applied 0 of 0" DID get
    // one. The quiet carve-out is justified only when everything asked for was
    // applied; nothing enforced that.
    const { container } = render(
      <ZtRunAiAccounting
        result={result({
          suggestions_received: 74,
          suggestions_applied: 0,
          dropped: Array.from({ length: 74 }, (_, i) =>
            drop({
              reason: "unknown_field",
              key: `ID-${i}`,
              field: "maturity",
            }),
          ),
        })}
      />,
    );
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(/AI applied\s*0\s*of 74/);
    expect(alert).toHaveTextContent(/Nothing was applied/);
    expect(headline(container)).toMatch(
      /every suggestion this run received was rejected or unrecognized/,
    );
  });

  it("does not cry failure when everything applied but nothing changed", () => {
    // A re-run over an already-drafted assessment applies every value and
    // changes none. "changing 0 fields across 0 capabilities" alone reads as a
    // failed run when it means the model agreed with everything.
    const { container } = render(
      <ZtRunAiAccounting
        result={result({ suggestions_received: 74, suggestions_applied: 74 })}
      />,
    );
    expect(screen.queryByRole("alert")).toBeNull();
    expect(headline(container)).toMatch(
      /Every suggestion matched what was already recorded/,
    );
  });

  it("carries a row count on the skip bullet, so it reconciles with the answers count", () => {
    // The skip bullet counts VALUES and the preserved-answers paragraph counts
    // ANSWERS. ZT charges two values per row, so a reader saw "10" beside "5"
    // with no way to bridge them from anything on screen.
    render(
      <ZtRunAiAccounting
        result={result({
          suggestions_received: 74,
          suggestions_applied: 64,
          dropped: Array.from({ length: 5 }, (_, i) =>
            drop({ reason: "protected", key: `ID-${i}`, values: 2 }),
          ),
        })}
      />,
    );
    const item = screen
      .getAllByRole("listitem")
      .map((li) => li.textContent ?? "")
      .find((t) => /skipped/.test(t));
    expect(item).toMatch(/10 suggested values across 5 capabilities skipped/);
  });

  it("renders hostile model text inertly and never as markup", () => {
    // `key` and `field` are model-authored and, transitively, seeded by a
    // client-role user's notes. Nothing pinned that they render as text.
    render(
      <ZtRunAiAccounting
        result={result({
          suggestions_received: 1,
          suggestions_applied: 0,
          dropped: [
            drop({
              reason: "unknown_key",
              key: '<img src=x onerror="alert(1)">',
              value: "<script>alert(2)</script>",
            }),
          ],
        })}
      />,
    );
    const alert = screen.getByRole("alert");
    expect(alert.querySelector("img")).toBeNull();
    expect(alert.querySelector("script")).toBeNull();
    expect(alert).toHaveTextContent('<img src=x onerror="alert(1)">');
  });

  it("names an empty capability code instead of rendering a blank", () => {
    render(
      <ZtRunAiAccounting
        result={result({
          suggestions_received: 1,
          suggestions_applied: 0,
          dropped: [
            drop({
              reason: "out_of_range",
              key: "",
              field: "current",
              value: "9",
            }),
          ],
        })}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "(no capability named)",
    );
  });

  it("tells the ALERT that nothing applied, not just the headline", () => {
    // The headline is demoted to polite whenever a failure block exists, so
    // with failures AND nothing applied the alert was the only assertive
    // utterance and it said "Some suggestions could not be applied" over a
    // total loss. The alert has to be a superset of the headline, not a
    // sibling of it.
    render(
      <ZtRunAiAccounting
        result={result({
          suggestions_received: 74,
          suggestions_applied: 0,
          dropped: [
            drop({
              reason: "out_of_range",
              key: "ID-1",
              field: "current",
              values: 3,
            }),
            drop({
              reason: "unknown_field",
              key: "ID-2",
              field: "maturity",
              values: 71,
            }),
          ],
        })}
      />,
    );
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(/Nothing was applied/);
    expect(alert).toHaveTextContent(/all 74 suggested values/);
    // The misleading token is gone from this state specifically.
    expect(alert).not.toHaveTextContent(
      /Some suggestions could not be applied/,
    );
  });

  it("stays CALM when every suggestion was skipped by design", () => {
    // The workflow `protected` exists for: a client submits every capability,
    // a consultant presses Run AI offline, everything is preserved. applied=0,
    // received=74, and NOTHING went wrong. Gating severity on `applied === 0`
    // alone shouted "every suggestion was rejected or unrecognized" over it —
    // #31 re-opened by the fix for #31's inverse.
    render(
      <ZtRunAiAccounting
        result={result({
          suggestions_received: 74,
          suggestions_applied: 0,
          dropped: Array.from({ length: 37 }, (_, i) =>
            drop({ reason: "protected", key: `ID-${i}`, values: 2 }),
          ),
        })}
      />,
    );
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByText(/Nothing was applied/)).toBeNull();
    expect(screen.queryByText(/rejected or unrecognized/)).toBeNull();
  });

  it("stays calm when every suggestion hit a locked row", () => {
    render(
      <ZtRunAiAccounting
        result={result({
          suggestions_received: 20,
          suggestions_applied: 0,
          dropped: Array.from({ length: 10 }, (_, i) =>
            drop({ reason: "locked", key: `ID-${i}`, values: 2 }),
          ),
        })}
      />,
    );
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("does not claim agreement when there was a shortfall", () => {
    // applied>0 and changed=0 is agreement ONLY if nothing was lost. With
    // unrecognized keys it printed "every suggestion matched" one paragraph
    // above "these are part of the shortfall".
    const { container } = render(
      <ZtRunAiAccounting
        result={result({
          suggestions_received: 111,
          suggestions_applied: 74,
          dropped: [
            drop({
              reason: "unknown_field",
              key: "ID-1",
              field: "confidence",
              values: 37,
            }),
          ],
        })}
      />,
    );
    expect(headline(container)).not.toMatch(/Every suggestion matched/);
    expect(screen.getByText(/37 values came back/)).toBeInTheDocument();
  });

  it("counts distinct capabilities on the skip bullet, not records", () => {
    // Two entries naming the same locked code are two records for ONE
    // capability. This number exists to reconcile with the answers count, so
    // counting records defeats its only purpose.
    render(
      <ZtRunAiAccounting
        result={result({
          suggestions_received: 6,
          suggestions_applied: 2,
          dropped: [
            drop({ reason: "locked", key: "ID-1", values: 2 }),
            drop({ reason: "locked", key: "ID-1", values: 2 }),
          ],
        })}
      />,
    );
    const item = screen
      .getAllByRole("listitem")
      .map((li) => li.textContent ?? "")
      .find((t) => /skipped/.test(t));
    expect(item).toMatch(/across 1 capability skipped/);
  });

  it("renders an inherited Object property as an unrecognized reason", () => {
    // `DROP_REASON_LABEL["toString"]` resolves to an inherited FUNCTION, which
    // `??` does not catch and React renders as nothing — the empty bullet the
    // guard exists to prevent. The previous test used "invented_later", which
    // is `undefined` and so passes under `??` too: it could not detect the
    // hardening it was added alongside.
    render(
      <ZtRunAiAccounting
        result={result({
          suggestions_received: 1,
          suggestions_applied: 0,
          dropped: [
            drop({ reason: "toString" as ZtDroppedSuggestion["reason"] }),
          ],
        })}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      /unrecognized reason "toString"/,
    );
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
          // `applied > 0` on purpose: the "Some suggestions could not be
          // applied" fallback this test pins is only reachable when the run
          // applied something. With nothing applied the lead states the total
          // instead, which is asserted separately.
          suggestions_received: 8,
          suggestions_applied: 3,
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
        .some((li) =>
          /2 suggested values across 1 capability skipped/.test(
            li.textContent ?? "",
          ),
        ),
    ).toBe(true);
  });
});
