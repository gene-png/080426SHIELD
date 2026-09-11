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
