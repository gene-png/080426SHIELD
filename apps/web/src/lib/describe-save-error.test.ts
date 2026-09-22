import { describe, expect, it } from "vitest";

import {
  clientFacingError,
  dashboardLoadReason,
  describeSaveError,
  serverReason,
  serverReasonCode,
} from "./describe-save-error";

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

  it("refuses the ARRAY detail a schema rejection produces", () => {
    // THESE TWO ASSERTIONS ARE REVERSED FROM WHAT THEY PINNED, deliberately,
    // and it is the behaviour that was wrong rather than the test.
    //
    // The old pair asserted that `serverReason` returned the Pydantic `msg`,
    // and joined several with a space. That is the raw validation dump core
    // principle 2 names as what a user-facing error must not be: "String
    // should have at most 8000 characters" is a limit in a vocabulary the
    // client never saw, for a field identified only in the `loc` nothing
    // renders. `CLAUDE.md` forbids weakening a test to reach green and
    // requires saying so out loud when the test itself is wrong -- this one
    // was, and the file it protected was rendering the dump to clients.
    //
    // The array is still HANDLED, which was the original point: returning
    // null is what stops the three admin `describeError` copies handing React
    // an array of objects. It is refused, not ignored.
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
    ).toBeNull();

    expect(
      serverReason({
        payload: {
          detail: [{ msg: "field a is wrong" }, { msg: "field b is wrong" }],
        },
      }),
    ).toBeNull();
  });

  it("refuses the ENVELOPED schema 422, on the code and not on presence", () => {
    // THE DEFECT. This is what `_handle_validation_error` produces for any
    // `max_length` or `extra="forbid"` violation -- copied off the producer,
    // not written to suit the parser. `IntakeSubmitRequest.notes` is
    // `max_length=4000` and the Step 5 textarea sets no `maxLength`, so a
    // client pasting a long paragraph submitted the intake and read
    // "Request validation failed." `clientFacingError` returned it because
    // `serverReason` had no guard at all, one surface over from
    // `SignUpForm.tsx`, which does.
    const schema422 = {
      status: 422,
      payload: {
        error: {
          code: 422,
          correlation_id: "c-3",
          reason: "schema_string_too_long",
          reasons: ["schema_string_too_long"],
          message: "Request validation failed.",
          details: [
            {
              loc: ["body", "services", 0, "notes"],
              msg: "String should have at most 4000 characters",
              type: "string_too_long",
            },
          ],
        },
      },
    };
    expect(serverReason(schema422)).toBeNull();
    expect(clientFacingError(schema422, "Failed to submit intake.")).toBe(
      "Failed to submit intake.",
    );

    // `schema_multiple`, the code for a body that fails several checks at
    // once. Asserted separately because a guard written against one literal
    // code rather than the PREFIX would pass the line above and fail here.
    expect(
      serverReason({
        status: 422,
        payload: {
          error: {
            reason: "schema_multiple",
            message: "Request validation failed.",
          },
        },
      }),
    ).toBeNull();
  });

  it("keeps a typed DOMAIN refusal, which is the other half", () => {
    // Without this, "withhold everything with a reason" passes every
    // assertion above while destroying every friendly message the API sends.
    // `target_stage_out_of_range` is a hand-written D-016 refusal with client
    // copy behind it; only the `schema_` namespace is synthesised.
    expect(
      serverReason({
        status: 422,
        payload: {
          error: {
            reason: "target_stage_out_of_range",
            message: "DoD ZTRA has stages 1-3.",
          },
        },
      }),
    ).toBe("DoD ZTRA has stages 1-3.");

    // And a code that merely CONTAINS the prefix elsewhere is not a schema
    // code. The guard anchors at the start, and this pins that it does.
    expect(
      serverReason({
        status: 409,
        payload: {
          error: {
            reason: "capability_schema_stale",
            message: "Re-run the extraction first.",
          },
        },
      }),
    ).toBe("Re-run the extraction first.");
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

  it("does NOT claim the value was restored unless it was", () => {
    // #371. This sentence used to be unconditional and was printed BEFORE the
    // re-fetch that restores the value -- so when that re-fetch failed, the
    // client sat looking at the refused value under a sentence saying it had
    // been replaced by server truth. A lie that something succeeded, which
    // core principle 2 forbids in as many words.
    //
    // `CLAUDE.md`: a success record must be written where the success is, not
    // before it. N-019, #47 and W1's accounting log were the first three; this
    // was the fourth, and the first read by a CLIENT rather than a developer.
    const text = describeSaveError({ payload: {} }, "CISA.ID.01");
    expect(text).not.toContain("has been restored");
    // It still says the thing the client needs immediately.
    expect(text).toContain("was not saved");
  });

  it("DOES claim it once the caller says the restore happened", () => {
    // The other half. Without this, a "fix" that deletes the sentence entirely
    // passes the test above while losing information the client wants in the
    // ordinary case.
    const text = describeSaveError({ payload: {} }, "CISA.ID.01", {
      restored: true,
    });
    expect(text).toContain("has been restored");
    expect(text).toContain("was not saved");
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

// ---------------------------------------------------------------------------
// #318, from the #295 review: the typed reason overrode the client copy in the
// NORMAL case rather than the exceptional one.
//
// THE PAYLOADS BELOW ARE NOT INVENTED. They are what
// `app/exceptions.py::_handle_http_exception` produces from the dict details
// raised in `routes/clients.py` -- it rewraps `{"reason": ..., "message": ...}`
// into `{error: {code, correlation_id, message, reason}}`. Authoring a fixture
// from what the consumer expects is the shape `CLAUDE.md` forbids, so these
// were copied off the producer.
//
// `grep -oE '"reason": "[a-z_]+"' apps/api/app/routes/clients.py | sort -u`
// returns exactly two codes as of 2026-09-20, and both appear here.
// ---------------------------------------------------------------------------

function notReleased(): unknown {
  return {
    status: 404,
    payload: {
      error: {
        code: 404,
        correlation_id: "c-1",
        reason: "dashboard_not_released",
        message: "No released Tech Debt report for this service yet.",
      },
    },
  };
}

function versionUnresolved(): unknown {
  return {
    status: 404,
    payload: {
      error: {
        code: 404,
        correlation_id: "c-2",
        reason: "dashboard_version_unresolved",
        message:
          "This report cannot be shown yet: we cannot establish which " +
          "assessment version it was built from. Please contact your " +
          "consultant.",
      },
    },
  };
}

describe("serverReasonCode", () => {
  it("reads the enveloped reason", () => {
    expect(serverReasonCode(notReleased())).toBe("dashboard_not_released");
    expect(serverReasonCode(versionUnresolved())).toBe(
      "dashboard_version_unresolved",
    );
  });

  it("is null when the server sent no code, rather than guessing one", () => {
    expect(serverReasonCode({ status: 404, payload: {} })).toBeNull();
    expect(
      serverReasonCode({ status: 500, payload: { detail: "boom" } }),
    ).toBeNull();
    expect(serverReasonCode(new Error("plain"))).toBeNull();
  });

  it("does not accept a blank code as a code", () => {
    // Whitespace is not a machine token. Returning "  " would put the caller
    // into the "the server said something specific" branch on nothing.
    expect(
      serverReasonCode({ status: 404, payload: { error: { reason: "   " } } }),
    ).toBeNull();
  });
});

describe("dashboardLoadReason", () => {
  it("withholds the server sentence for an ordinary not-released 404", () => {
    // THE DEFECT. `serverReason` returns a sentence here, and the page's
    // `{reason ?? ourCopy}` therefore never reached `ourCopy` -- in the most
    // common state of the page. Asserting BOTH halves, because a helper that
    // returned null for everything would pass the first line alone.
    expect(serverReason(notReleased())).toBe(
      "No released Tech Debt report for this service yet.",
    );
    expect(dashboardLoadReason(notReleased())).toBeNull();
  });

  it("keeps the server sentence for an unresolved parent version", () => {
    // THE OTHER HALF, and the reason #244 was filed: this refusal is NOT "no
    // released report yet" -- there is one, and what is missing is the link
    // saying which assessment it was built from. A page that prints its own
    // not-released copy here tells the client something false.
    const text = dashboardLoadReason(versionUnresolved());
    expect(text).toContain("which assessment version");
    expect(text).not.toContain("hasn't been released");
  });

  it("prefers the server for a code it has never seen", () => {
    // The error direction, asserted rather than described. This is a deny-list
    // of one: an unknown code means a situation the generic copy was not
    // written for, so the specific message wins.
    const unknown = {
      status: 409,
      payload: {
        error: { reason: "dashboard_wedged_somehow", message: "Specifics." },
      },
    };
    expect(dashboardLoadReason(unknown)).toBe("Specifics.");
  });

  it("prefers the server when there is a message but no code at all", () => {
    // A refusal carrying no `reason` at all. Falling back to the page's
    // not-released copy would manufacture a diagnosis out of the ABSENCE of
    // one -- the shape `CLAUDE.md` records as missing data defaulting to a
    // positive claim.
    //
    // THIS CLASS IS RAISED INSIDE THE DASHBOARD ROUTES THEMSELVES, and an
    // earlier version of this comment said it came from "outside these
    // routes" -- false, and positioned exactly where the next person would
    // check, so it would have stopped them looking in the right file.
    // `routes/clients.py` raises `detail="Client not found."` at the top of
    // all five dashboard routes; `dependencies.py::current_client` and
    // `tenant.py` raise their own string-detail 404s on the same request.
    // `_handle_http_exception` puts a string detail straight into
    // `error["message"]` with no `reason` key.
    //
    // So this branch renders the raw string: an admin whose active-client
    // cookie names a deleted client reads "No client with that id." under
    // "Dashboard not available yet". PRE-EXISTING -- `serverReason` did the
    // same before #318. Preferring the server is still right for these: the
    // page's not-released copy would be FALSE over a wrong-tenant refusal.
    //
    // NOT FIXED HERE, and now genuinely tracked: **#394**, tier-3 + post-mvp.
    //
    // This comment read "filed rather than fixed here" while nothing was
    // filed. It is a DIFFERENT defect from #393 (that one is the Python
    // docstring's pointer) and from #365 (proxy LABELS on admin components,
    // not a raw server sentence on a dashboard), so it needed its own number
    // rather than being folded into either.
    //
    // #394 records the fix direction too, because the obvious one is wrong:
    // do NOT fall back to the page's not-released copy here. That copy is
    // FALSE over a wrong-tenant refusal, which is #244. These refusals need a
    // typed `{reason, message}` detail, like the conversion #298 did for
    // `routes/tech_debt.py`.
    const nocode = {
      status: 502,
      payload: { error: { message: "Upstream call failed." } },
    };
    expect(dashboardLoadReason(nocode)).toBe("Upstream call failed.");
  });

  it("returns null when the server sent nothing usable", () => {
    expect(dashboardLoadReason({ status: 500, payload: {} })).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// #318, from the #295 review: the internal-string defect's twins.
//
// `ZtProxyError` is `super(`ZT proxy ${status}`)`. `describeSaveError` was
// written for that in #283 and applied to the SAVE path only, so the LOAD and
// SUBMIT paths in the same components still rendered `err.message`.
// ---------------------------------------------------------------------------

class ZtProxyErrorLike extends Error {
  // The production shape, copied off `lib/zt/client.ts` rather than invented:
  // the constructor discards the reason into a label and keeps the real thing
  // on `payload`. A fixture that carried the reason in `message` would agree
  // with a broken implementation by construction.
  constructor(
    public readonly status: number,
    public readonly payload: unknown,
  ) {
    super(`ZT proxy ${status}`);
  }
}

describe("clientFacingError", () => {
  it("never shows the internal proxy label", () => {
    const err = new ZtProxyErrorLike(409, {
      error: {
        reason: "assessment_not_draft",
        message: "This assessment is no longer editable.",
      },
    });
    const text = clientFacingError(err, "Submit failed.");

    expect(text).toBe("This assessment is no longer editable.");
    // Both halves of the label, because "409" alone also appears in plenty of
    // legitimate copy and "ZT proxy" alone would miss a reworded prefix.
    expect(text).not.toContain("ZT proxy");
    expect(text).not.toContain("409");
  });

  it("falls back to the caller's generic when the server sent nothing", () => {
    // The fallback is reached on ABSENCE of a server sentence -- never by
    // showing `err.message`, which is what the old code did here.
    const err = new ZtProxyErrorLike(500, {});
    expect(clientFacingError(err, "Failed to load.")).toBe("Failed to load.");
  });

  it("falls back for a plain Error, whose message is also internal", () => {
    // A TypeError from fetch reads "Failed to fetch" / "fetch failed". Not a
    // proxy label, and still not client copy.
    expect(
      clientFacingError(new TypeError("fetch failed"), "Network error."),
    ).toBe("Network error.");
  });

  it("prefers the server sentence over the generic, which is the point", () => {
    // THE OTHER HALF. A helper that always returned the fallback would pass
    // every assertion above while discarding exactly what #244 fought for.
    const err = new ZtProxyErrorLike(422, {
      error: {
        reason: "target_stage_out_of_range",
        message: "DoD ZTRA has stages 1-3.",
      },
    });
    expect(clientFacingError(err, "Submit failed.")).toBe(
      "DoD ZTRA has stages 1-3.",
    );
  });
});
