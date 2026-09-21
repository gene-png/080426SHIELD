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

  it("every dashboard page handles an API error", () => {
    // THE EXEMPTION THIS REPLACES, and why it had to go (#318, from the #295
    // review). The per-page assertion below used to open with
    //
    //     if (!src.includes("ApiError")) return;
    //
    // "only pages that actually handle an API error are in scope". True, and
    // it is a SILENT EXEMPTION that vitest reports as a pass -- in a file whose
    // docstring promises the page set is derived so "a sixth dashboard is
    // covered the day it is added". A sixth dashboard that forgot to catch was
    // covered by nothing, and the report said it was covered.
    //
    // The population is not "pages that catch"; it is "pages that show a client
    // a failed load". A dashboard that does not catch is not out of scope -- it
    // is a dashboard with no error surface at all, which is its own defect and
    // must be stated here rather than skipped. So the predicate is asserted
    // instead of branched on.
    const silent = PAGES.filter(
      (p) => !readFileSync(p, "utf8").includes("ApiError"),
    );
    expect(
      silent,
      `these dashboard pages do not handle an ApiError at all. A failed load on
one of them is an unhandled throw rather than a sentence a client can read, and
the typed-reason assertions below would have SKIPPED them in silence.`,
    ).toEqual([]);
  });

  it.each(PAGES.map((p) => [p.slice(p.indexOf("dashboards")), p] as const))(
    "%s consults the typed reason before falling back to its own copy",
    (_label, path) => {
      const src = readFileSync(path, "utf8");

      // `dashboardLoadReason`, NOT `serverReason` -- and the distinction is the
      // whole of #318's first finding. `serverReason` returns the server's
      // sentence whenever one arrived, and the ordinary not-released 404 always
      // carries one, so `{reason ?? ourCopy}` rendered the API's
      // developer-facing wording in the page's MOST COMMON state and the copy
      // written for a client was unreachable. The typed reason was overriding
      // the normal case instead of the exceptional one.
      //
      // Asserted as an EXCLUSION as well as an inclusion, because a page that
      // called both would satisfy a bare `includes` while still doing the wrong
      // thing on whichever line ran.
      expect(
        src.includes("dashboardLoadReason("),
        `this page catches an ApiError and never consults the server's reason, so
a typed explanation the API took care to write is discarded and the hardcoded
sentence is printed in its place. That is #244.`,
      ).toBe(true);

      // THE BARE TOKEN, not `reason = serverReason(`. The narrower form was
      // the first version and it did not deliver what this comment claims: a
      // page that called BOTH -- `const r = serverReason(err); ... reason = r;`
      // -- satisfies the inclusion, misses that regex, and still renders the
      // wrong sentence on whichever line runs. Extra whitespace or a prettier
      // wrap on a long assignment miss it too.
      //
      // Safe as an exclusion because no dashboard page has a legitimate call:
      // `serverReason(` -- with the paren -- appears in none of the five, and
      // the explanatory comments in those files write `serverReason` without
      // one, so they do not trip it. `dashboardLoadReason(` does not contain
      // `serverReason(`, so the inclusion above is unaffected.
      expect(
        src.includes("serverReason("),
        `this page assigns its rendered copy from serverReason(). That renders
the server's developer-facing sentence over this page's client copy in the
ordinary not-released case, which is #318. Use dashboardLoadReason().`,
      ).toBe(false);

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
    // ASSERT THE COUNT THE FILTER SELECTED, BEFORE READING ITS RESULT. The
    // population is built from a literal, so a page that rewords that sentence
    // leaves it silently and `offenders` stays empty over a page nobody
    // checked -- "I could not look" sharing an exit with "nothing to complain
    // about", which the first `it` in this file prevents for the directory
    // scan and did not do here.
    const candidates = PAGES.filter((p) =>
      /We couldn't load|couldn't load/.test(readFileSync(p, "utf8")),
    );
    expect(
      candidates.length,
      `only ${candidates.length} of ${PAGES.length} dashboard pages carry a
generic load-failure sentence, so the assertion below examined fewer pages than
exist. A page that reworded it left this check in silence.`,
    ).toBe(PAGES.length);

    const offenders = candidates.filter(
      (p) => !/\{reason \?\?/.test(readFileSync(p, "utf8")),
    );
    expect(offenders).toEqual([]);
  });
});
