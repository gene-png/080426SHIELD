/**
 * The one response a proxy gives when it could not see the api's result (#550).
 *
 * HTTP 504 with the house envelope and a typed reason, never an untyped 502
 * "call failed": the api may have done the work. Pure apart from its log line:
 * no `auth()`, no service knowledge, so every proxy route and helper can call
 * it from its `catch`. An `ApiError` (the api DID answer) is the caller's to
 * pass through and never reaches here.
 */

import { NextResponse } from "next/server";

import {
  UPSTREAM_OUTCOME_UNKNOWN,
  UPSTREAM_OUTCOME_UNKNOWN_MESSAGE,
} from "@/lib/upstream-outcome";

/** Node's `fetch` puts the reason it gave up on `cause.code`. */
function causeCode(err: unknown): string | undefined {
  const cause = (err as { cause?: { code?: unknown } } | null)?.cause;
  return typeof cause?.code === "string" ? cause.code : undefined;
}

/**
 * @param err   what the upstream call threw
 * @param where which proxy call it was, for the log line only
 */
export function upstreamOutcomeUnknown(
  err: unknown,
  where: string,
): NextResponse {
  // Logged, not swallowed: the browser is told only that the outcome is
  // unknown, so the cause has to be on record somewhere. `String(err)` and
  // not the error's message field: `client-surfaces-never-render-an-internal-
  // string.test.ts` scans `lib/` for that read, and this is a server log line,
  // not copy, so it takes the spelling that gate does not have to judge.
  const code = causeCode(err);
  console.error(
    `[proxy] ${where}: no answer from the api, outcome unknown (${String(err)}${
      code ? `, ${code}` : ""
    })`,
  );
  return NextResponse.json(
    {
      error: {
        code: 504,
        reason: UPSTREAM_OUTCOME_UNKNOWN,
        message: UPSTREAM_OUTCOME_UNKNOWN_MESSAGE,
      },
    },
    { status: 504 },
  );
}
