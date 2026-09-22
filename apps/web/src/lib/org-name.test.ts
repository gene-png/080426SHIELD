import { describe, expect, it } from "vitest";

import { UNNAMED_ORG_LABEL, isNamedOrg, orgDisplayName } from "./org-name";

/**
 * D-080 (#254) made `legal_name` nullable: NULL means nobody has named the
 * organisation, which is the state every self-serve signup starts in.
 *
 * These are the two questions the web layer asks about that column — "may I
 * print this?" and "what do I print?" — and they are separated on purpose. A
 * single helper returning `legal_name ?? label` would make every caller that
 * needs the BOOLEAN test the label instead, which is how the string becomes a
 * condition again.
 */
describe("isNamedOrg", () => {
  it("is false for the state the API now sends for an unnamed org", () => {
    expect(isNamedOrg(null)).toBe(false);
  });

  it("is false when the field is absent entirely", () => {
    expect(isNamedOrg(undefined)).toBe(false);
  });

  it("is false for an empty or whitespace-only name", () => {
    // Not a name, however it got there — a round-tripped "" is as unnamed as
    // a NULL, and a caller asking "can I print this" wants one answer.
    expect(isNamedOrg("")).toBe(false);
    expect(isNamedOrg("   ")).toBe(false);
  });

  it("is true for a name a human gave", () => {
    expect(isNamedOrg("Atlas Defense Solutions")).toBe(true);
  });
});

describe("orgDisplayName", () => {
  it("labels an unnamed org rather than returning null", () => {
    // The point of the helper: callers sort, lowercase and interpolate this
    // result, and `null.toLowerCase()` is a crash rather than a blank.
    expect(orgDisplayName(null)).toBe(UNNAMED_ORG_LABEL);
    expect(orgDisplayName(undefined)).toBe(UNNAMED_ORG_LABEL);
    expect(orgDisplayName("")).toBe(UNNAMED_ORG_LABEL);
  });

  it("returns the name unchanged when there is one", () => {
    expect(orgDisplayName("Atlas Defense Solutions")).toBe(
      "Atlas Defense Solutions",
    );
  });

  it("always returns something printable", () => {
    // The property every call site relies on, asserted directly rather than
    // inferred from the cases above.
    for (const input of [null, undefined, "", "  ", "Northwind"]) {
      expect(typeof orgDisplayName(input)).toBe("string");
      expect(orgDisplayName(input).length).toBeGreaterThan(0);
    }
  });
});
