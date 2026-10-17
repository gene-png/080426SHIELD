/**
 * "The api may have finished, and we cannot tell" (#550).
 *
 * A proxy whose `fetch` rejected (Node's 300 s headers timeout, a reset, a
 * refused connection) never saw the api's answer. #550 measured the api
 * finishing anyway: an extraction the caller had given up on wrote its
 * `llm_calls` row and created the draft list. "Failed" is false there, and the
 * natural response to it is a retry that sends the client's data out again.
 *
 * Client-safe on purpose (no `next/server`), so the components that must tell
 * this outcome apart can import the code without pulling in the server builder,
 * which lives in `upstream-outcome-unknown.ts`.
 */

/**
 * The typed reason a proxy answers when it could not see the result of a
 * WRITE (any method but GET/HEAD). A read answers `UPSTREAM_READ_FAILED`
 * instead (#1130), so a guard keyed on this code never sees a failed read.
 */
export const UPSTREAM_OUTCOME_UNKNOWN = "upstream_outcome_unknown";

/**
 * Generic on purpose: the builder is shared by every proxy, so it names no
 * service. The surfaces where a retry is costly add where to check.
 */
export const UPSTREAM_OUTCOME_UNKNOWN_MESSAGE =
  "We couldn't confirm whether this finished. It may still complete; check before trying again.";

/**
 * #1130: the same missing answer, for a READ. Nothing "may still complete"
 * when the call was a GET, so the sentence above is false there; a read says
 * it could not load. Its own reason, so no surface keyed on #550's code
 * (Run AI's "outcome unknown" lock) can mistake a failed read for a write.
 */
export const UPSTREAM_READ_FAILED = "upstream_read_failed";

/** Approved verbatim on #736 (issuecomment-6225076633, option b). */
export const UPSTREAM_READ_FAILED_MESSAGE =
  "SHIELD's server didn't send a complete answer, so this couldn't be loaded. Reload the page to try again.";
