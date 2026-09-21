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
 * ## Three payload shapes, and the third is the one the house helpers miss
 *
 * `{error: {message}}`  the house envelope, from `app/exceptions.py`
 * `{detail: "..."}`     FastAPI's default for a plain `HTTPException`
 * `{detail: [...]}`     a SCHEMA rejection — `detail` is an ARRAY of error
 *                       objects, which is what `extra="forbid"` and any
 *                       `max_length` violation produce
 *
 * The `describeError` copies in the three admin workspaces read
 * `payload?.detail` and would hand React an array of objects for the third,
 * which renders as `[object Object]` or throws. Handled here.
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

/** The server's own sentence, or null when it did not send a usable one. */
export function serverReason(err: unknown): string | null {
  if (!hasPayload(err)) return null;
  const payload = err.payload as ErrorPayload | undefined;
  if (!payload) return null;

  const enveloped = payload.error?.message;
  if (typeof enveloped === "string" && enveloped.trim())
    return enveloped.trim();

  const detail = payload.detail;
  if (typeof detail === "string" && detail.trim()) return detail.trim();

  // The array form. Each entry is `{loc, msg, type, ...}`; `msg` is the human
  // half and is the only field worth showing. Joined rather than truncated to
  // the first, because a body can fail two fields at once and reporting one is
  // how a client fixes half a problem and resubmits.
  if (Array.isArray(detail)) {
    const messages = detail
      .map((d) =>
        typeof d === "object" && d !== null
          ? (d as { msg?: unknown }).msg
          : null,
      )
      .filter((m): m is string => typeof m === "string" && m.trim().length > 0);
    if (messages.length) return messages.join(" ");
  }
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
 * ## Why preferring the server UNCONDITIONALLY is right here
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
export function describeSaveError(err: unknown, subject: string): string {
  const reason = serverReason(err);
  const because = reason ? ` ${reason}` : "";
  return `${subject} was not saved.${because} The value on screen has been restored to what the server has. Your consultant can help if this keeps happening.`;
}
