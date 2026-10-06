import { describe, expect, it } from "vitest";

import { inputLine } from "./inputs";

describe("Inputs panel rows per service (#876)", () => {
  it("names the qualifier when the server sends one", () => {
    expect(
      inputLine({
        kind: "zt",
        engaged: true,
        status: "released",
        version: 1,
        qualifier: "CISA ZTMM 2.0",
      }),
    ).toBe("Zero Trust (CISA ZTMM 2.0): released");
    expect(
      inputLine({
        kind: "zt",
        engaged: true,
        status: null,
        version: null,
        qualifier: "DoD ZT Reference Architecture",
      }),
    ).toBe("Zero Trust (DoD ZT Reference Architecture): not started");
  });

  it("keeps the bare label with no qualifier", () => {
    expect(
      inputLine({
        kind: "zt",
        engaged: true,
        status: "released",
        version: 1,
        qualifier: null,
      }),
    ).toBe("Zero Trust: released");
  });
});
