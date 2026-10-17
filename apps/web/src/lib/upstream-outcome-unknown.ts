/**
 * The response a proxy gives when it could not see the api's result: #550's
 * "outcome unknown" for a write, and #1130's "could not load" for a read
 * (GET/HEAD), chosen by the upstream call's method.
 *
 * HTTP 504 with the house envelope and a typed reason, never an untyped 502
 * "call failed": for a write, the api may have done the work. Pure apart from its log line:
 * no `auth()`, no service knowledge, so every proxy route and helper can call
 * it from its `catch`. An `ApiError` (the api DID answer) is the caller's to
 * pass through and never reaches here.
 */

import { NextResponse } from "next/server";

import {
  UPSTREAM_OUTCOME_UNKNOWN,
  UPSTREAM_OUTCOME_UNKNOWN_MESSAGE,
  UPSTREAM_READ_FAILED,
  UPSTREAM_READ_FAILED_MESSAGE,
} from "@/lib/upstream-outcome";

/** Node's `fetch` puts the reason it gave up on `cause.code`. */
function causeCode(err: unknown): string | undefined {
  const cause = (err as { cause?: { code?: unknown } } | null)?.cause;
  return typeof cause?.code === "string" ? cause.code : undefined;
}

/** A GET or HEAD changes nothing by HTTP contract, so its missing answer is not "unknown". A read sent as a POST still gets the #550 body (it over-warns). */
function isRead(method: string): boolean {
  const m = method.toUpperCase();
  return m === "GET" || m === "HEAD";
}

/**
 * @param err    what the upstream call threw
 * @param where  which proxy call it was, for the log line only
 * @param method the UPSTREAM call's method (#1130). Required, so every caller
 *               states it: a GET or HEAD answers `upstream_read_failed`, anything
 *               else the #550 body.
 */
export function upstreamOutcomeUnknown(
  err: unknown,
  where: string,
  method: string,
): NextResponse {
  // Logged, not swallowed: the browser is told only that the outcome is
  // unknown, so the cause has to be on record somewhere. `String(err)` and
  // not the error's message field: `client-surfaces-never-render-an-internal-
  // string.test.ts` scans `lib/` for that read, and this is a server log line,
  // not copy, so it takes the spelling that gate does not have to judge.
  const code = causeCode(err);
  const read = isRead(method);
  console.error(
    `[proxy] ${where}: no answer from the api, ${
      read ? "read failed" : "outcome unknown"
    } (${method} ${String(err)}${code ? `, ${code}` : ""})`,
  );
  if (read) {
    return NextResponse.json(
      {
        error: {
          code: 504,
          reason: UPSTREAM_READ_FAILED,
          message: UPSTREAM_READ_FAILED_MESSAGE,
        },
      },
      { status: 504 },
    );
  }
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
