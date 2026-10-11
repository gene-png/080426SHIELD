import { describe, expect, it } from "vitest";

import { inputLine } from "./inputs";

/**
 * #474 D' (Gene, #736 5984218862): a released CSF assessment with no in-scope
 * Playbook rows feeds no CSF finding, and the Inputs panel says so, only after
 * "released" (#736 6087027524, Q3).
 */
describe("Inputs panel, a CSF record with no Playbook scores (#474 D')", () => {
  it("appends the note after released", () => {
    expect(
      inputLine({
        kind: "csf",
        engaged: true,
        status: "released",
        version: 1,
        no_playbook_scores: true,
      }),
    ).toBe("NIST CSF: released, no Playbook scores");
  });

  it("says nothing extra before release", () => {
    expect(
      inputLine({
        kind: "csf",
        engaged: true,
        status: "approved",
        version: 1,
        no_playbook_scores: true,
      }),
    ).toBe("NIST CSF: approved, not yet released");
    expect(
      inputLine({
        kind: "csf",
        engaged: true,
        status: "draft",
        version: 1,
        no_playbook_scores: true,
      }),
    ).toBe("NIST CSF: in progress (draft)");
  });

  it("says nothing extra when the Playbook has rows, or the flag is absent", () => {
    expect(
      inputLine({
        kind: "csf",
        engaged: true,
        status: "released",
        version: 1,
        no_playbook_scores: false,
      }),
    ).toBe("NIST CSF: released");
    expect(
      inputLine({ kind: "csf", engaged: true, status: "released", version: 1 }),
    ).toBe("NIST CSF: released");
  });
});
