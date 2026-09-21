import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * No admin workspace swallows a fetch failure into a state that reads as
 * "still loading" (#292).
 *
 * ## The shape
 *
 * A component fetches, sets state on success, and catches with a comment:
 *
 *     } catch {
 *       // Non-blocking; the score/gap panels show their own loading state.
 *     }
 *
 * The comment is the defect, not the excuse. The panels DO show a loading
 * state, and it is indistinguishable from a slow network — so a consultant
 * looking at a permanently-spinning card cannot tell in-flight from failed
 * from never-attempted. `CLAUDE.md`: a value that is `null` for BOTH "still
 * loading" and "request failed" makes its callers conflate the two.
 *
 * ## Two sub-shapes, and the second is worse
 *
 * Most of these leave an AMBIGUITY. Two asserted a known NEGATIVE: the
 * deliverable catches said the card "shows 'not finalized yet'", which is a
 * claim about the SERVER made on the strength of a request that failed, and a
 * consultant can act on it by finalizing a second time. Missing data defaults
 * to unconfirmed, never to a known negative.
 *
 * ## Derived, because the issue's list was a sample
 *
 * #292 named four sites. Sweeping the SHAPE — a `try` that sets state whose
 * `catch` neither reverts nor surfaces — found twelve across the repo, nine of
 * them in these four workspaces. A guard over the four files would go stale on
 * the fifth workspace; this reads the directory.
 */

const ADMIN = join(process.cwd(), "src/components/admin");

function walk(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...walk(full));
    else if (/\.tsx$/.test(entry) && !/\.test\.tsx$/.test(entry))
      out.push(full);
  }
  return out;
}

const FILES = walk(ADMIN);

/** A `catch` whose entire body is comments — it reverts nothing and says nothing. */
const SILENT_CATCH = /\}\s*catch\s*\{\s*(?:\/\/[^\n]*\n\s*)+\}/;

describe("admin workspaces never present a failed fetch as an ongoing load", () => {
  it("finds the admin components at all", () => {
    // Fail closed. A moved or renamed directory would otherwise turn every
    // assertion below into zero cases, which vitest reports as success.
    expect(FILES.length).toBeGreaterThanOrEqual(15);
  });

  it("no component swallows a failure into a comment-only catch", () => {
    const offenders = FILES.filter((f) =>
      SILENT_CATCH.test(readFileSync(f, "utf8")),
    ).map((f) => f.slice(f.indexOf("src")));

    expect(
      offenders,
      `these admin components catch a failure and neither revert nor surface it,
so the panel is left in a state a consultant reads as "still loading". Set a
refresh-error state and render it; "non-blocking" is not the same as silent.`,
    ).toEqual([]);
  });
});
