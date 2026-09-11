import { describe, expect, it } from "vitest";

import {
  assumedTargetCount,
  assumedTargetNote,
  gapHint,
  targetIsWhollyTheClients,
  type TargetProvenance,
} from "./value-summary";

/**
 * The value card may not call a target "yours" unless it was (#207).
 *
 * The defect: `hint: "Capabilities below your target maturity stage."` was
 * unconditional, over a SUM whose summands are each counted against a target
 * resolved per service. A client who chose nothing, or whose stored choice was
 * out of range, read a possessive about a stage they had never seen.
 *
 * These tests are the reason this lives in `lib/` rather than inside the
 * component: a test importing `ValueLoopCard` pulls in `@shield/design-system`
 * and cannot be collected locally at all (#175), and a test that never runs is
 * not coverage. The component's own test covers the rendering.
 */

function zt(over: Partial<TargetProvenance> = {}): TargetProvenance {
  return {
    services: 1,
    defaulted: 0,
    unusable: 0,
    unit: "stage",
    noun: "Zero Trust reports",
    ...over,
  };
}

describe("assumedTargetCount", () => {
  it("is 0 when every summand used the client's own choice", () => {
    expect(assumedTargetCount(zt())).toBe(0);
  });

  it("sums the two kinds of assumption", () => {
    expect(
      assumedTargetCount(zt({ services: 5, defaulted: 2, unusable: 1 })),
    ).toBe(3);
  });

  it("is NULL, never 0, when the counts were never measured", () => {
    // The API sends null for both whenever the figure is null: a kind goes
    // unresolved wholesale and returns on the first unresolvable service, so
    // any tally reached by then describes a prefix of a sum nobody published.
    // A 0 would render as "nothing was assumed" over something unmeasured.
    expect(
      assumedTargetCount(zt({ defaulted: null, unusable: null })),
    ).toBeNull();
    expect(assumedTargetCount(zt({ defaulted: null }))).toBeNull();
    expect(assumedTargetCount(zt({ unusable: null }))).toBeNull();
  });
});

describe("gapHint", () => {
  it("says YOUR target when the client chose every one of them", () => {
    expect(gapHint(zt(), "Capabilities")).toBe(
      "Capabilities below your target maturity stage.",
    );
  });

  it("drops the possessive as soon as ONE summand was assumed", () => {
    // The sharp case, and the reason the rule is "every" rather than "most":
    // four of five reports on the client's own stage still leaves one figure in
    // the sum counted against something they did not choose, and the card shows
    // one number.
    expect(gapHint(zt({ services: 5, defaulted: 1 }), "Capabilities")).toBe(
      "Capabilities below the target maturity stage.",
    );
  });

  it("drops it for an unusable choice too, not only for an absent one", () => {
    expect(gapHint(zt({ unusable: 1 }), "Capabilities")).toBe(
      "Capabilities below the target maturity stage.",
    );
  });

  it("keeps the possessive when the counts are unknown", () => {
    // `targetIsWhollyTheClients` is `=== 0`, so null is not 0 and the
    // possessive would be dropped. Pinned because the alternative spelling
    // (`!== 0`, or a truthiness test) flips this silently and the null case is
    // the unresolved one, where no figure renders at all.
    expect(
      targetIsWhollyTheClients(zt({ defaulted: null, unusable: null })),
    ).toBe(false);
    expect(
      gapHint(zt({ defaulted: null, unusable: null }), "Capabilities"),
    ).toBe("Capabilities below the target maturity stage.");
  });

  it("uses the unit it is given, so CSF does not say stage", () => {
    expect(gapHint({ ...zt(), unit: "tier" }, "Subcategories")).toBe(
      "Subcategories below your target maturity tier.",
    );
  });
});

describe("assumedTargetNote", () => {
  it("says nothing when there is nothing to disclose", () => {
    expect(assumedTargetNote(zt())).toBeNull();
  });

  it("says nothing when the counts were never measured", () => {
    expect(
      assumedTargetNote(zt({ defaulted: null, unusable: null })),
    ).toBeNull();
  });

  it("omits the fraction when every report was assumed", () => {
    // "3 of 3" is noise; the client has no report on their own target at all
    // and the sentence should say so without arithmetic.
    expect(assumedTargetNote(zt({ services: 3, defaulted: 3 }))).toBe(
      "Counted against the standard stage — no stage chosen at intake.",
    );
  });

  it("carries the denominator when only some were", () => {
    // Without it, "2 reports use the standard stage" does not say whether that
    // is 2 of 2 or 2 of 9, which is the difference between a figure that is
    // mostly theirs and one that is not theirs at all.
    expect(assumedTargetNote(zt({ services: 9, defaulted: 2 }))).toBe(
      "2 of 9 Zero Trust reports counted against the standard stage — no stage chosen at intake.",
    );
  });

  it("NEVER collapses a discarded choice into having made none", () => {
    // The load-bearing one. `lib/dashboards/zt.ts::targetFault` refuses this
    // collapse for a single service and says why: telling a client they made no
    // choice when they made one that was discarded is a lie in their own words,
    // and only the second is answerable by re-asking them. The aggregate must
    // not undo that at the last step.
    const note = assumedTargetNote(
      zt({ services: 4, defaulted: 0, unusable: 2 }),
    );
    expect(note).toBe(
      "2 of 4 Zero Trust reports counted against the standard stage — the stage on file could not be used.",
    );
    expect(note).not.toMatch(/no stage chosen/);
  });

  it("reports BOTH faults when both are present, in a fixed order", () => {
    // Fixed rather than data-dependent, so two clients with the same two faults
    // read the same sentence.
    expect(
      assumedTargetNote(zt({ services: 6, defaulted: 1, unusable: 2 })),
    ).toBe(
      "3 of 6 Zero Trust reports counted against the standard stage — no stage chosen at intake; the stage on file could not be used.",
    );
  });

  it("speaks CSF's vocabulary when given CSF's", () => {
    expect(
      assumedTargetNote({
        services: 2,
        defaulted: 2,
        unusable: 0,
        unit: "tier",
        noun: "NIST CSF reports",
      }),
    ).toBe("Counted against the standard tier — no tier chosen at intake.");
  });

  it("names no action, because the card has none to offer", () => {
    // A user-facing string naming an action must name a control that exists and
    // works today. A client cannot change their engagement target from this
    // card. Asserted rather than left to reviewer memory, because "ask your
    // analyst to confirm it" is exactly the sentence this repo has already
    // shipped over a control that did not work.
    const notes = [
      assumedTargetNote(zt({ services: 3, defaulted: 3 })),
      assumedTargetNote(zt({ services: 3, unusable: 3 })),
      assumedTargetNote(zt({ services: 3, defaulted: 1, unusable: 1 })),
    ];
    for (const note of notes) {
      expect(note).not.toMatch(
        /\b(ask|contact|update|set|change|confirm|re-?enter)\b/i,
      );
    }
  });
});
