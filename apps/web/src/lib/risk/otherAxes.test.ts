import { describe, expect, it } from "vitest";

import { otherAxesCell } from "./otherAxes";

/**
 * #736 6094620397, Risk E item 4. Expected strings written out from the
 * ruling: comma-joined display names, an empty cell for `[]`, "Not recorded"
 * for NULL.
 */
describe("otherAxesCell", () => {
  it("joins the display names", () => {
    expect(otherAxesCell(["prevention", "response"])).toBe(
      "Prevention, Response",
    );
  });

  it("prints nothing for the claim that there is no other axis", () => {
    expect(otherAxesCell([])).toBe("");
  });

  it("prints Not recorded when nothing was recorded", () => {
    expect(otherAxesCell(null)).toBe("Not recorded");
    expect(otherAxesCell(undefined)).toBe("Not recorded");
  });
});
