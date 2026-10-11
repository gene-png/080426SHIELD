import { describe, expect, it } from "vitest";

import { inputLine } from "./inputs";

/**
 * #474 D', R10 (#736 6102665946): when the CSF Playbook measured, the Inputs
 * panel states how many targeted subcategories have no tier row both scored
 * and targeted. Approved copy, with its singular; only after "released", and
 * only when the count is above 0.
 */
describe("Inputs panel, targeted CSF subcategories with no row both scored and targeted (R10, R11)", () => {
  const csf = {
    kind: "csf",
    engaged: true,
    version: 1,
    no_playbook_scores: false,
  };

  it("states the singular count after released", () => {
    expect(
      inputLine({
        ...csf,
        status: "released",
        unscored_targeted_subcategories: 1,
      }),
    ).toBe(
      "NIST CSF: released. 1 targeted subcategory has no row with both a score and a target, and raises no finding.",
    );
  });

  it("states the plural count after released", () => {
    expect(
      inputLine({
        ...csf,
        status: "released",
        unscored_targeted_subcategories: 2,
      }),
    ).toBe(
      "NIST CSF: released. 2 targeted subcategories have no row with both a score and a target, and raise no finding.",
    );
  });

  it("says nothing extra at 0, when absent, or before release", () => {
    expect(
      inputLine({
        ...csf,
        status: "released",
        unscored_targeted_subcategories: 0,
      }),
    ).toBe("NIST CSF: released");
    expect(inputLine({ ...csf, status: "released" })).toBe(
      "NIST CSF: released",
    );
    expect(
      inputLine({
        ...csf,
        status: "approved",
        unscored_targeted_subcategories: 1,
      }),
    ).toBe("NIST CSF: approved, not yet released");
  });
});

/**
 * R11 (#736 6103383277): scores and targets exist but never share a row. Its
 * own fragment, after "released" only; the true no-scores fragment is kept.
 */
describe("Inputs panel, no Playbook row with both a score and a target (R11)", () => {
  const csf = { kind: "csf", engaged: true, version: 1 };

  it("appends the fragment after released", () => {
    expect(
      inputLine({
        ...csf,
        status: "released",
        no_playbook_scores: false,
        no_shared_playbook_row: true,
      }),
    ).toBe(
      "NIST CSF: released, no Playbook row with both a score and a target",
    );
  });

  it("keeps the no-scores fragment for the true no-scores case", () => {
    expect(
      inputLine({
        ...csf,
        status: "released",
        no_playbook_scores: true,
        no_shared_playbook_row: false,
      }),
    ).toBe("NIST CSF: released, no Playbook scores");
  });

  it("says nothing extra before release", () => {
    expect(
      inputLine({
        ...csf,
        status: "approved",
        no_playbook_scores: false,
        no_shared_playbook_row: true,
      }),
    ).toBe("NIST CSF: approved, not yet released");
  });
});
