import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { proxyMessage, TechDebtProxyError } from "@/lib/tech_debt/client";

/**
 * The Approve handler must show the server's refusal (#231).
 *
 * ## The defect this guards
 *
 * `approve_capability_list` raises a typed 409 naming the one remedy that
 * exists — "upload a replacement list" — when the list was discarded. The
 * handler that triggers it had `try { … } finally { setApproving(false); }`
 * and **no `catch`**: the promise rejected unhandled, the button went from
 * "Approving…" back to "Approve list", and the consultant was shown nothing.
 * It was the only mutating handler in the workspace without a catch.
 *
 * A `catch` alone would not have been enough either. `TechDebtProxyError`'s
 * message is `"Tech-debt proxy 409"`, so the `err.message` spelling used by
 * `onDiscard` would have printed a status code where a remedy was available —
 * the same defect #283 found in the self-assessment components.
 *
 * ## Two halves, deliberately
 *
 * `proxyMessage` owns what the consultant reads and is tested directly. It
 * lives in `lib/tech_debt/client.ts`, beside the error class it unwraps, so
 * this file can reach it WITHOUT importing the component — a test importing
 * `TechDebtWorkspace` cannot be collected locally at all (#175), and a test
 * that never runs is not coverage.
 *
 * The WIRING — that every mutating handler has a catch at all — is a source
 * sweep, because nothing under `components/admin` has a render harness for a
 * component of this size and building one to assert a paragraph is a larger
 * change than the fix. Same instrument, and same stated bound, as
 * `dashboards-render-the-typed-reason.test.ts` (#244).
 *
 * **What the sweep does NOT prove:** that the message reaches a browser. Only
 * e2e shows that, and no spec asserts this paragraph today.
 */

// Newlines normalised before anything parses this. The working tree is Windows
// and the file is CRLF, so the chunk bound below silently found nothing, every
// chunk ran to EOF, and each handler was satisfied by a NEIGHBOUR's catch. The
// sweep passed with `onApprove`'s catch deleted — #72's shape, in the file
// written to catch it, found by red-on-revert rather than by review.
const SOURCE = readFileSync(
  join(__dirname, "TechDebtWorkspace.tsx"),
  "utf8",
).replace(/\r\n/g, "\n");

/** Marks a chunk whose end could not be located. See the assertion below. */
const UNBOUNDED = " UNBOUNDED";

/** Each `async function on…` declaration in the component, body included. */
function handlers(src: string): Array<[string, string]> {
  const out: Array<[string, string]> = [];
  const decl = /\n {2}async function (\w+)\(/g;
  let m: RegExpExecArray | null;
  while ((m = decl.exec(src)) !== null) {
    // Bounded at the two-space-indented closing brace, so a chunk holds its own
    // function and nothing else. Without the bound a chunk runs to EOF and a
    // neighbour's `catch` satisfies it — which is exactly what happened.
    const end = src.indexOf("\n  }\n", m.index);
    // Unbounded is NOT "nothing to complain about": it is "I could not look".
    // Reported as a sentinel the assertion refuses, so a parse that breaks
    // cannot read as code that passes.
    out.push([m[1], end === -1 ? UNBOUNDED : src.slice(m.index, end)]);
  }
  return out;
}

describe("the Tech Debt workspace surfaces what the server said", () => {
  it("finds the handlers at all", () => {
    // Fail loudly rather than sweep nothing: a reformat that breaks this parse
    // must not read as "every handler is fine".
    const names = handlers(SOURCE).map(([n]) => n);
    expect(names).toContain("onApprove");
    expect(names.length).toBeGreaterThanOrEqual(3);
  });

  it.each(handlers(SOURCE).map(([name, body]) => [name, body] as const))(
    "%s handles a rejected request",
    (name, body) => {
      expect(
        body,
        `the ${name} chunk has no end, so this assertion is vacuous`,
      ).not.toBe(UNBOUNDED);
      expect(
        /\bcatch\s*[({]/.test(body),
        `${name} awaits a request and has no catch, so a typed refusal rejects
unhandled and the consultant is shown nothing at all. That is #231's remedy
string going nowhere.`,
      ).toBe(true);
    },
  );

  it("reads the D-016 envelope the API actually emits", () => {
    const err = new TechDebtProxyError(409, {
      error: {
        reason: "capability_list_discarded",
        message:
          "This capability list was discarded and cannot be approved. Upload a replacement list instead.",
      },
    });
    expect(proxyMessage(err, "fallback")).toMatch(/upload a replacement list/i);
  });

  it("reads a bare detail string too", () => {
    const err = new TechDebtProxyError(409, {
      detail: "This capability list has been released and is locked.",
    });
    expect(proxyMessage(err, "fallback")).toMatch(/released and is locked/);
  });

  it("never shows the proxy's own message, which is only a status code", () => {
    // Asserted rather than assumed: `err.message` is the spelling a sibling
    // handler uses, and it reads plausibly at the call site.
    const err = new TechDebtProxyError(409, undefined);
    expect(err.message).toMatch(/proxy 409/);
    expect(proxyMessage(err, "Approving the list failed.")).toBe(
      "Approving the list failed.",
    );
  });

  it("falls back for a non-proxy failure", () => {
    expect(proxyMessage(new Error("boom"), "fallback")).toBe("boom");
    expect(proxyMessage("not an error", "fallback")).toBe("fallback");
  });
});
