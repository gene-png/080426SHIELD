import { readFileSync } from "node:fs";
import { readdirSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Every client dashboard must render the server's TYPED reason, not just its
 * HTTP status (#244).
 *
 * ## The defect this guards
 *
 * The API spent a week learning to say WHY a number is missing — which target
 * it was computed against, which inputs were withheld, which link is absent.
 * The dashboards threw all of it away and keyed their copy on `err.status ===
 * 404`, then printed a hardcoded sentence.
 *
 * `_unresolved_parent`'s message was authored specifically to avoid a
 * falsehood: *"The MESSAGE does not reuse 'no released report yet', which
 * would be false -- there is one; what is missing is the link saying which
 * assessment it was built from."* Keying on the status printed the exact
 * sentence that message was written to avoid.
 *
 * ## Why this is a SOURCE test and not a render test
 *
 * These pages are async server components. Nothing under `apps/web/src/app`
 * has a unit-test harness, and building one for a server component to assert a
 * paragraph is a larger change than the fix. The honest alternatives were a
 * source assertion or nothing.
 *
 * It is the same instrument as `test_audit_gate_collects_only_this_branch.py`:
 * where the defect is one line in a file, a check that the line is still right
 * is the proportionate guard. It fails loudly if the file moves, rather than
 * passing over a file it can no longer find.
 *
 * **What it does NOT prove:** that the reason reaches a browser. Only e2e can
 * show that, and no spec asserts this paragraph today — the two that touch
 * this screen assert the HEADING. Stated so the coverage is not overread.
 *
 * ## Derived, not listed
 *
 * The page set is read off the directory, so a sixth dashboard is covered the
 * day it is added rather than the day someone remembers this file. That is the
 * point: #244 is about the boundary, and a new page written to the old pattern
 * is the boundary failing again.
 */

const DASHBOARDS = join(process.cwd(), "src/app/dashboards");

function pageFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const p = join(dir, entry);
    if (statSync(p).isDirectory()) out.push(...pageFiles(p));
    else if (entry === "page.tsx") out.push(p);
  }
  return out;
}

const PAGES = pageFiles(DASHBOARDS);

describe("client dashboards render the server's typed reason", () => {
  it("finds the dashboard pages at all", () => {
    // Fail loudly rather than sweep nothing. Without this, moving or renaming
    // the directory turns every assertion below into zero cases, which vitest
    // reports as success — "I could not look" sharing an exit with "nothing to
    // complain about".
    expect(PAGES.length).toBeGreaterThanOrEqual(5);
  });

  it.each(PAGES.map((p) => [p.slice(p.indexOf("dashboards")), p] as const))(
    "%s consults the typed reason before falling back to its own copy",
    (_label, path) => {
      const src = readFileSync(path, "utf8");

      // Only pages that actually handle an API error are in scope; one that
      // never catches has no reason to discard.
      if (!src.includes("ApiError")) return;

      expect(
        src.includes("serverReason("),
        `this page catches an ApiError and never reads the server's reason, so a
typed explanation the API took care to write is discarded and the hardcoded
sentence is printed in its place. That is #244.`,
      ).toBe(true);

      // And the reason must WIN. Capturing it and then rendering the hardcoded
      // string regardless would satisfy the check above while changing nothing
      // a client sees.
      expect(
        /\{reason \?\?/.test(src),
        `this page reads the server's reason but does not render it in
preference to its own copy. Capturing a value and not showing it is the same
outcome as never reading it.`,
      ).toBe(true);
    },
  );

  it("no dashboard prints its fallback sentence unconditionally", () => {
    // The inverse assertion, and the one that would catch a future edit that
    // "simplifies" the ternary back. A page whose fallback is not guarded by
    // `reason ??` is printing it whatever the server said.
    const offenders = PAGES.filter((p) => {
      const src = readFileSync(p, "utf8");
      return src.includes("We couldn't load") && !/\{reason \?\?/.test(src);
    });
    expect(offenders).toEqual([]);
  });
});
