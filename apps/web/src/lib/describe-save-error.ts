/**
 * What to tell a user whose write did not save (#283).
 *
 * ## Why this exists rather than `err.message`
 *
 * The proxy error classes throw away the server's reason in their own
 * constructor: `ZtProxyError` is `super(\`ZT proxy ${status}\`)` and
 * `CsfProxyError` is `super(\`CSF proxy ${status}\`)`. The reason is kept on
 * `.payload` and nothing reads it. A first draft of #283's fix used
 * `err.message`, so a client whose consultant had just approved the assessment
 * would have read:
 *
 *     That change was not saved. ZT proxy 409 ...
 *
 * — a raw internal string in client-facing copy, which core principle 2
 * forbids. It passed its test only because the test fabricated a plain
 * `Error`, a shape the production code cannot produce.
 *
 * ## Three payload shapes, and ONLY THE FIRST IS WHAT THIS API SENDS
 *
 * `{error: {…}}`        the house envelope, from `app/exceptions.py`. The live
 *                       wire format for BOTH handlers: a string `detail`
 *                       becomes `error.message`, and a schema rejection's array
 *                       lands on `error.details` — plural, inside the envelope.
 * `{detail: "..."}`     FastAPI's default for a plain `HTTPException`,
 *                       DEFENSIVE ONLY here
 * `{detail: [...]}`     FastAPI's default for a schema rejection, also
 *                       DEFENSIVE ONLY, and refused rather than rendered
 *
 * **The "defensive only" is measured, and this table used to assert the
 * opposite** — it said the array form is "what `extra="forbid"` and any
 * `max_length` violation produce", present tense, as the live format.
 * `register_exception_handlers` registers handlers for both `HTTPException` and
 * `RequestValidationError` and both return `content={"error": {...}}`;
 * `grep -rn 'content={"detail\|"detail":' apps/api/app` and
 * `grep -rn "detail=\[" apps/api` both return nothing. So no route can emit a
 * bare top-level `detail`, and the two branches below are a harmless superset
 * kept for an upstream that is not this API.
 *
 * The correction matters because `describe-save-error.test.ts` already says
 * this, in the test for the array branch — so the truth was written where the
 * subject was DISCUSSED and the false version left standing where a reader
 * looks it up. That is the correct-at-the-instruction rule failing inside one
 * commit.
 *
 * The array is still HANDLED rather than ignored: the `describeError` copies in
 * the three admin workspaces read `payload?.detail` and would hand React an
 * array of objects, which renders as `[object Object]` or throws. Here it
 * returns null, because a Pydantic `msg` is the raw validation dump core
 * principle 2 names as what a user-facing error must not be.
 *
 * ## Duck-typed, not `instanceof`
 *
 * Two proxy error classes exist (`ZtProxyError`, `CsfProxyError`) and more
 * will. Keying on the SHAPE — a `payload` and a numeric `status` — lets one
 * helper serve both without importing either, and without a list that goes
 * stale on the third.
 */

type ErrorPayload = {
  error?: { message?: unknown; reason?: unknown };
  detail?: unknown;
};

function hasPayload(
  err: unknown,
): err is { payload?: unknown; status?: unknown } {
  return typeof err === "object" && err !== null && "payload" in err;
}

/**
 * The server's machine CODE for this refusal, or null when it sent none.
 *
 * ## Why this exists beside `serverReason`, which is the message
 *
 * A caller choosing between the server's sentence and its own copy must make
 * that choice on the CODE, never on whether a message arrived. Testing the
 * message's presence is a PRESENCE test on an optional field, and this repo
 * has already paid for one: #317 put the internal string
 * "Request validation failed." under the Email field of the public sign-up
 * page, because `SignUpForm.tsx` chose between typed copy and a friendly
 * fallback by testing that `reason` was present.
 *
 * The dashboards did the same thing one surface over, in the opposite
 * direction: `{reason ?? ourCopy}` renders the server's sentence whenever one
 * exists, and the ordinary not-released 404 always carries one. So the copy
 * written for a client was unreachable in the most common state of the page.
 *
 * `error.reason` is the field the API's own handler promises -- a dict detail
 * `{reason, message}` is rewrapped into `{error: {code, correlation_id,
 * message, reason}}` by `_handle_http_exception`, which is why this reads the
 * enveloped form and not `detail`.
 */
export function serverReasonCode(err: unknown): string | null {
  if (!hasPayload(err)) return null;
  const payload = err.payload as ErrorPayload | undefined;
  const code = payload?.error?.reason;
  return typeof code === "string" && code.trim() ? code.trim() : null;
}

/**
 * #556 (the owner's decision): a client report WITHHELD because it was built
 * over an ATT&CK assessment scored against another catalog. The API answers a
 * typed 409 carrying the client sentence. ONE predicate for every page that
 * must tell this refusal apart from a failure -- the ATT&CK and Risk dashboards,
 * and the Results page's probe -- so none of them can drift into treating it as
 * a crash. Keyed on the status AND the code: a 409 of any other reason is still
 * an error.
 */
export function isCatalogWithheld(err: unknown): boolean {
  if (!hasPayload(err) || err.status !== 409) return false;
  return serverReasonCode(err) === "attack_catalog_mismatch";
}

/**
 * The codes whose MESSAGE a dashboard must not show in place of its own copy.
 *
 * Exactly one, and it is the ordinary case: a report that has not been
 * released yet. The API says "No released Tech Debt report for this service
 * yet." The page says "This Technical Debt report hasn't been released to your
 * organization yet. It will appear here once your SHIELD analyst releases it."
 *
 * The second sentence is the one a client needs -- it uses the product's name
 * rather than the internal shorthand, says whose organization, and names the
 * next thing that happens. The first is a correct statement of fact written
 * for a developer reading a 404.
 *
 * ## The error direction is deliberate: unknown codes PREFER the server
 *
 * This is a deny-list of one, not an allow-list, so a code nobody has seen
 * before renders the server's message. That is the safe direction: a new code
 * means a situation the generic copy was not written for, and #244 exists
 * because a page printed "no released report yet" over a refusal that meant
 * something else entirely. Silence toward the specific message is the failure
 * that issue records; verbosity toward it is recoverable.
 */
const GENERIC_COPY_IS_BETTER = new Set(["dashboard_not_released"]);

/**
 * The sentence a dashboard should render for a failed load, or null to mean
 * "use your own copy".
 *
 * Callers pass the error and get back the server's message ONLY where the
 * server is saying something their copy does not cover. Derived in one place
 * rather than repeated across five dashboards, so the five cannot drift --
 * and so the decision has somewhere to be tested that is not a page.
 */
export function dashboardLoadReason(err: unknown): string | null {
  const code = serverReasonCode(err);
  if (code !== null && GENERIC_COPY_IS_BETTER.has(code)) return null;
  return serverReason(err);
}

/**
 * The namespace `apps/api/app/exceptions.py` reserves for a reason SYNTHESISED
 * from Pydantic's own error `type` (#285) — `schema_string_too_short`,
 * `schema_value_error`, and `schema_multiple` when a request fails several
 * checks at once. Every one of them rides on the same internal message,
 * "Request validation failed.", and none has client copy behind it.
 *
 * Duplicated across the LANGUAGE boundary rather than derived, because there is
 * no build step shared by the FastAPI app and this bundle. It is NOT duplicated
 * within this bundle: `SignUpForm.tsx` imports it from here. That file used to
 * hold its own literal, and `SCHEMA_REASON_PREFIX` in `exceptions.py` still
 * names `SignUpForm.tsx` in its docstring as the TS-side site — which is one
 * hop from here rather than wrong, because that import is the first thing a
 * reader arriving there sees. Repointing the Python docstring at this file is
 * NOT DONE HERE — `exceptions.py` is outside this PR's territory — and is
 * tracked in **#393**. This clause read "is filed" when nothing was, then
 * "NOT FILED" citing a search that returned nothing, and that same search
 * returned #393 within the hour. The longer note is at the matching clause in
 * `SignUpForm.tsx`; the short version is that a search result is a measurement
 * with a timestamp, not a property, so cite the number instead.
 *
 * BOTH DIRECTIONS ARE PINNED, and this paragraph asserted that one was not. It
 * read "a Python-side edit reddens NOTHING. `test_schema_422_typed_reason.py`
 * imports the constant from the module under test, so it follows any change
 * silently." That file holds
 * `test_the_schema_namespace_is_the_literal_the_web_layer_spells_out`, whose
 * body is `assert exceptions.SCHEMA_REASON_PREFIX == "schema_"` — spelled out,
 * not imported — so a Python-side edit goes red there. The TS side is pinned by
 * `schemaReasonFallback` in `SignUpForm.test.tsx` and again in
 * `describe-save-error.test.ts`, both of which spell the literal rather than
 * import it. If this prefix changes in one language and not the other, #317
 * returns on the public sign-up page — but a test now says so.
 *
 * The sentence was INHERITED from `SignUpForm.tsx` when the constant moved, and
 * copying it turned one wrong claim into two. Corrected in place at both sites
 * rather than deleted: it arrived under "stated rather than left to be
 * discovered", which is the phrasing that stops the next reader checking, and a
 * reader who believed it would build a cross-language pin that already ships.
 */
export const SCHEMA_REASON_PREFIX = "schema_";

/**
 * The server's own sentence, or null when it did not send one FIT FOR A PERSON.
 *
 * ## Two things the server sends that are not client copy
 *
 * **A schema-level 422.** Its message is the fixed internal string
 * "Request validation failed." and its reason is a `schema_*` machine token
 * with nothing behind it. Withheld on the VALUE of the code, never on whether
 * a message arrived — a presence test here is #317 exactly, and
 * `serverReasonCode`'s own docstring forbids it. `SignUpForm.tsx` guards this
 * envelope the same way, one surface over; this is the shared helper the five
 * client surfaces reach it through, and it had no guard at all.
 *
 * Reachable today, not hypothetical: `IntakeSubmitRequest.notes` is
 * `max_length=4000` and the Step 5 textarea sets no `maxLength`, so a pasted
 * paragraph put "Request validation failed." under a client's intake.
 *
 * **The ARRAY `detail` form.** Each entry is `{loc, msg, type, ...}` and `msg`
 * is Pydantic's own wording — "String should have at most 8000 characters",
 * naming a limit in a vocabulary the client never saw, for a field identified
 * only in the `loc` this never renders. That is the raw validation dump core
 * principle 2 forbids. An earlier version of this function JOINED those msgs
 * into client copy and a test pinned the join as intended; both are corrected
 * rather than kept, because the behaviour was the defect and the test was
 * certifying it.
 *
 * Refusing both returns null, so the caller renders its OWN copy. That is a
 * loss of specificity and it is the right side to err on: the caller's generic
 * was written for a person, and neither of these was.
 */
export function serverReason(err: unknown): string | null {
  if (!hasPayload(err)) return null;
  const payload = err.payload as ErrorPayload | undefined;
  if (!payload) return null;

  const code = serverReasonCode(err);
  if (code !== null && code.startsWith(SCHEMA_REASON_PREFIX)) return null;

  const enveloped = payload.error?.message;
  if (typeof enveloped === "string" && enveloped.trim())
    return enveloped.trim();

  const detail = payload.detail;
  if (typeof detail === "string" && detail.trim()) return detail.trim();

  // The array form falls through to null. It is the un-enveloped spelling of
  // the same schema rejection the code check above withholds, so rendering it
  // here would reinstate through `detail` what was just refused through
  // `error.reason`.
  return null;
}

/**
 * What to show a CLIENT when a call failed and there is no richer local copy.
 *
 * Returns the server's own typed sentence where it sent one, and `fallback`
 * otherwise. **It never returns `err.message`**, which is the whole point.
 *
 * ## The defect this exists to end
 *
 * Every proxy error class throws its own reason away in its constructor:
 *
 *     super(`ZT proxy ${status}`)      super(`CSF proxy ${status}`)
 *     super(`Intake proxy ${status}`)  super(`ATT&CK proxy ${status}`)
 *
 * ...nine of them, `grep -rn "super(\`" src/lib/*\/client.ts`. So
 * `err instanceof Error ? err.message : "Failed to load."` renders
 * **"ZT proxy 409"** to a client -- a raw internal string in client-facing
 * copy, which core principle 2 forbids.
 *
 * `describeSaveError` below was written for exactly this (#283) and was
 * applied to the SAVE path only. The LOAD and SUBMIT paths in the same
 * components kept the old shape, twelve lines away.
 *
 * ## Why preferring the server over the FALLBACK is right here
 *
 * "Unconditionally" is what this said, and it was wrong in the one direction
 * that costs a client: `serverReason` now withholds a schema-level 422 and the
 * array `detail` dump, because neither is copy. Preferring the server is about
 * the choice between its sentence and `fallback`, not about whether everything
 * it sends is fit to render.
 *
 * It is not right everywhere, and the difference is the only thing worth
 * knowing about this function.
 *
 * The client dashboards face the same choice and answer it PER REASON CODE,
 * not wholesale -- and the distinction is load-bearing, because a sentence
 * saying they "answer it the other way" would license destroying a fix.
 *
 * Their 404 has more than one cause. For `dashboard_not_released` the page's
 * own copy is richer -- it names the product, whose organization and the next
 * step -- so the API's "No released X report for this service yet." is a
 * downgrade. For `dashboard_version_unresolved` the server's sentence is the
 * whole point: `_unresolved_parent` is written specifically NOT to say "no
 * released report yet", because there IS one and what is missing is the link
 * saying which assessment it came from. Printing the not-released copy there
 * is exactly the #244 defect.
 *
 * So the deciding property is a fact about the PAIR (server message, local
 * copy) for a given refusal -- not about the call site, and not about which
 * module the caller lives in. PR #362 withholds for the first code only and
 * keeps the second; anything that withholds wholesale reinstates #244.
 *
 * The callers here pass a bare generic: "Failed to load.", "Submit failed.",
 * "Network error.". No server sentence is worse than those, so there is
 * nothing to protect.
 *
 * **The property that decides it is whether the local copy carries
 * information the server's does not** -- never which module the caller lives
 * in. Written down because the two situations look like one shape, differ in
 * the one thing that matters, and moving either answer into the other's
 * position would be a regression that reads as consistency.
 */
export function clientFacingError(err: unknown, fallback: string): string {
  return serverReason(err) ?? fallback;
}

/**
 * The full sentence shown to the client.
 *
 * **No "try again" imperative.** The most likely failure here is a 409 — the
 * consultant approved the assessment while the client was still typing — and
 * retrying can never succeed for a non-DRAFT assessment. `CLAUDE.md`: a
 * user-facing string naming an action must name a control that exists and
 * works TODAY. So this says what happened and who to ask, and does not
 * instruct.
 */
export function describeSaveError(
  err: unknown,
  subject: string,
  opts: { restored?: boolean } = {},
): string {
  const reason = serverReason(err);
  const because = reason ? ` ${reason}` : "";

  // THE RESTORATION CLAIM IS OPT-IN, because it was being made BEFORE the
  // restoration happened -- and stayed on screen when it never happened.
  //
  // Both self-assessment surfaces called this, then re-fetched server truth,
  // and their `catch` said "the message above still stands and is the honest
  // one: we cannot show what the server has". The message said the opposite:
  // that the value HAD BEEN restored. So on a failed re-fetch the client sat
  // looking at the refused value under a sentence telling them it had been
  // replaced -- a lie that something succeeded, which core principle 2 forbids
  // in as many words (#371).
  //
  // `CLAUDE.md`: a success record must be written where the success is, not
  // before it. Recorded after N-019, #47 and W1's accounting log; this was the
  // fourth, and the first where the false record is read by a CLIENT rather
  // than by a developer.
  //
  // Callers show the bare message immediately -- nobody should wait on a
  // re-fetch to learn their edit failed -- and replace it with
  // `{ restored: true }` only once the re-fetch has resolved. Each sentence is
  // then true at the moment it is on screen.
  const restored = opts.restored
    ? " The value on screen has been restored to what the server has."
    : "";
  return `${subject} was not saved.${because}${restored} Your consultant can help if this keeps happening.`;
}
