import { describe, expect, it } from "vitest";

import { describeSaveError, serverReason } from "./describe-save-error";

/**
 * The half of #283 that CAN be run locally.
 *
 * The component test cannot be collected in `verify-in-worktree` — issue #175,
 * `packages/design-system` cannot resolve `clsx` — so it has never been
 * executed. This file imports no component and therefore runs, which makes it
 * the only local evidence that the message logic is right.
 *
 * That is a deliberate split, not a substitute: the component test still owns
 * the WIRING (does anything call this, is the revert visible), and this owns
 * the CONTENT. Testing only this would be the pin-the-unit-not-the-wiring
 * mistake the rule in `CLAUDE.md` names.
 */
describe("serverReason", () => {
  it("reads the house envelope", () => {
    expect(
      serverReason({
        payload: { error: { message: "This assessment is locked." } },
      }),
    ).toBe("This assessment is locked.");
  });

  it("reads FastAPI's plain string detail", () => {
    expect(
      serverReason({
        payload: { detail: "Your self-assessment is no longer editable." },
      }),
    ).toBe("Your self-assessment is no longer editable.");
  });

  it("reads the ARRAY detail a schema rejection produces", () => {
    // The shape `extra="forbid"` and any `max_length` violation emit. The
    // `describeError` copies in the three admin workspaces read `payload.detail`
    // unconditionally and would hand React an array of objects here.
    expect(
      serverReason({
        payload: {
          detail: [
            {
              loc: ["body", "notes"],
              msg: "String should have at most 8000 characters",
            },
          ],
        },
      }),
    ).toBe("String should have at most 8000 characters");
  });

  it("joins a multi-field rejection rather than reporting the first", () => {
    // Reporting one of two is how a client fixes half a problem and resubmits.
    expect(
      serverReason({
        payload: {
          detail: [{ msg: "field a is wrong" }, { msg: "field b is wrong" }],
        },
      }),
    ).toBe("field a is wrong field b is wrong");
  });

  it("returns null rather than an internal string when there is no reason", () => {
    // THE REGRESSION THIS FILE EXISTS FOR. `ZtProxyError`'s own constructor is
    // `super(`ZT proxy ${status}`)`, so a first draft that read `err.message`
    // put "ZT proxy 409" in front of a client. Anything unreadable must yield
    // null so the caller falls back to its own copy.
    expect(serverReason({ payload: {} })).toBeNull();
    expect(serverReason({ payload: { detail: [] } })).toBeNull();
    expect(
      serverReason({ payload: { detail: [{ loc: ["body"] }] } }),
    ).toBeNull();
    expect(serverReason(new Error("ZT proxy 409"))).toBeNull();
    expect(serverReason(undefined)).toBeNull();
  });
});

describe("describeSaveError", () => {
  it("names the row, so the client knows which answer was lost", () => {
    // The alert renders once, at the bottom of a page carrying up to 106
    // subcategories. "That change" is not something a client can act on.
    const text = describeSaveError({ payload: {} }, "CISA.ID.01");
    expect(text).toContain("CISA.ID.01");
  });

  it("carries the server's sentence when there is one", () => {
    const text = describeSaveError(
      { payload: { detail: "Your self-assessment is no longer editable." } },
      "CISA.ID.01",
    );
    expect(text).toContain("no longer editable");
  });

  it("never prints an internal proxy string", () => {
    // The discriminating assertion against the defect this replaced.
    const text = describeSaveError(new Error("ZT proxy 409"), "CISA.ID.01");
    expect(text).not.toContain("ZT proxy");
    expect(text).not.toContain("409");
  });

  it("does not tell the client to try again", () => {
    // The likeliest failure is a 409 — the consultant approved the assessment
    // while the client was typing — and retrying can never succeed for a
    // non-DRAFT assessment. `CLAUDE.md`: a user-facing string naming an action
    // must name a control that exists and works TODAY.
    const text = describeSaveError({ payload: {} }, "CISA.ID.01");
    expect(text.toLowerCase()).not.toContain("try again");
  });
});
