import { describe, expect, it } from "vitest";

import { readFailureReason } from "./describe-save-error";

/**
 * RR-2 (for #1121), design note §3.2. A failed READ shows the server's
 * sentence where it has one, EXCEPT #550's: "We couldn't confirm whether this
 * finished..." is about a write whose outcome is unknown, and a list read
 * changed nothing. The sentence is spelled out here, not imported.
 */
const OUTCOME_UNKNOWN =
  "We couldn't confirm whether this finished. It may still complete; check before trying again.";

function failure(status: number, payload: unknown) {
  return { status, payload };
}

describe("readFailureReason", () => {
  it("withholds #550's upstream_outcome_unknown sentence", () => {
    expect(
      readFailureReason(
        failure(504, {
          error: {
            code: 504,
            reason: "upstream_outcome_unknown",
            message: OUTCOME_UNKNOWN,
          },
        }),
      ),
    ).toBeNull();
  });

  it("withholds a schema_* refusal, as serverReason does", () => {
    expect(
      readFailureReason(
        failure(422, {
          error: {
            code: 422,
            reason: "schema_missing",
            message: "Request validation failed.",
          },
        }),
      ),
    ).toBeNull();
  });

  it("passes a plain server sentence through", () => {
    expect(
      readFailureReason(
        failure(404, {
          error: { code: 404, message: "No client with that id." },
        }),
      ),
    ).toBe("No client with that id.");
  });
});
