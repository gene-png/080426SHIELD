import { describe, expect, it } from "vitest";

import {
  INPUTS_RULE,
  REVIEW_PENDING_NOTE,
  inputLine,
  sourceStateNote,
} from "./inputs";

describe("Inputs panel words (#737)", () => {
  it("states Gene's rule verbatim", () => {
    expect(INPUTS_RULE).toBe(
      "This register is a draft until every assessment it draws on is final.",
    );
  });

  it("names each input and its state", () => {
    expect(
      inputLine({
        kind: "attack",
        engaged: true,
        status: "approved",
        version: 1,
      }),
    ).toBe("ATT&CK coverage: approved, not yet released");
    expect(
      inputLine({ kind: "zt", engaged: true, status: "released", version: 2 }),
    ).toBe("Zero Trust: released");
    expect(
      inputLine({ kind: "csf", engaged: true, status: "draft", version: 1 }),
    ).toBe("NIST CSF: in progress (draft)");
    expect(
      inputLine({
        kind: "tech_debt",
        engaged: true,
        status: null,
        version: null,
      }),
    ).toBe("Technology debt list: not started");
    expect(
      inputLine({ kind: "csf", engaged: false, status: null, version: null }),
    ).toBe("NIST CSF: not engaged");
  });

  it("labels a finding from an unreleased input, and says nothing otherwise", () => {
    expect(sourceStateNote("draft")).toBe(" (from a draft assessment)");
    expect(sourceStateNote(null)).toBeNull();
  });

  it("names a finding awaiting review (DRAFT copy, with the advisor)", () => {
    expect(REVIEW_PENDING_NOTE).toBe(" (computed status awaiting review)");
  });
});
