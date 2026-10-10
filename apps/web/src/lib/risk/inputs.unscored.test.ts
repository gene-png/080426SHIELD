import { describe, expect, it } from "vitest";

import { inputLine } from "./inputs";

/**
 * #474 D', R10 (#736 6102665946): when the CSF Playbook measured, the Inputs
 * panel states how many targeted subcategories have no tier row both scored
 * and targeted. Approved copy, with its singular; only after "released", and
 * only when the count is above 0.
 */
describe("Inputs panel, targeted CSF subcategories with no recorded scores (R10)", () => {
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
      "NIST CSF: released. 1 targeted subcategory has no recorded scores and raises no finding.",
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
      "NIST CSF: released. 2 targeted subcategories have no recorded scores and raise no finding.",
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
