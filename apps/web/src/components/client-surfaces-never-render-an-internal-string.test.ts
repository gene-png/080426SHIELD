import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * No CLIENT-facing surface renders a caught error's `.message` (#318).
 *
 * ## What the string actually is
 *
 * Nine proxy error classes discard the server's reason in their own
 * constructor -- `super(\`ZT proxy ${status}\`)`, `super(\`Intake proxy
 * ${status}\`)`, and so on. The reason survives on `.payload` and `.message`
 * is the internal label. So
 *
 *     err instanceof Error ? err.message : "Failed to load."
 *
 * puts **"ZT proxy 409"** in front of a paying client. Core principle 2 names
 * a raw internal string as what a user-facing error must not be, and
 * `describeSaveError` was built for it in #283 -- then applied to the SAVE
 * path only, leaving the LOAD and SUBMIT paths in the same components twelve
 * lines away.
 *
 * ## Derived, and the population is stated rather than assumed
 *
 * The set is every file under the client-facing component directories, read
 * off disk, so a new intake step or self-assessment panel is covered the day
 * it is added.
 *
 * `components/admin/**` is DELIBERATELY out of scope and it is not clean: ten
 * sites there have the same shape. A Kentro consultant reading "CSF proxy 409"
 * is a real defect and a different tier from a client reading it, so it is
 * filed rather than swept in here -- and named here so the exemption reads as
 * a decision rather than an oversight.
 *
 * ## No silent skip
 *
 * Every assertion below is over the whole set at once. There is no per-file
 * branch that can `return` early, because that is exactly how the dashboards'
 * own guard came to report a pass over a page it never examined.
 */

// DERIVED, not a list of directories. The first version named
// `components/self-assessment` and `components/intake` and stated ONE
// exclusion, so a reader concluded client-facing = everything minus admin.
// It is not: `components/assessments/` rendered "Intake proxy 409" to a
// client on /assessments, and `lib/messages/client.ts` put "Messages proxy
// 500" in front of a client messaging their consultant -- through
// `MessageThread` on `app/self-assessment/[serviceId]/page.tsx`, THE PAGE
// THE FIRST VERSION OF THIS GUARD WAS WRITTEN FOR. A two-directory list
// reported clean over both.
//
// The predicate is stated and then applied: every `.ts`/`.tsx` under
// `components/` or `lib/`, MINUS the admin surfaces, which are a different
// tier and are filed as #365.
const SEARCH_ROOTS = ["src/components", "src/lib"];

//: Each exclusion named with its reason. The two lib helpers are admin-only
//: by their CONSUMERS, which a path does not say, so they are listed rather
//: than gestured at.
const EXCLUDED: Array<[RegExp, string]> = [
  [
    /[\/]components[\/]admin[\/]/,
    "admin surfaces: a consultant, not a client (#365)",
  ],
  [/[\/]lib[\/]admin[\/]/, "admin API helpers (#365)"],
  [
    /[\/]lib[\/]risk[\/]client\.ts$/,
    "describeRiskError is consumed only by components/admin/risk/RiskRegisterDashboard.tsx (#365)",
  ],
];

function walk(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...walk(full));
    else if (/\.tsx?$/.test(entry) && !/\.test\.tsx?$/.test(entry))
      out.push(full);
  }
  return out;
}

const FILES = SEARCH_ROOTS.flatMap((r) => walk(join(process.cwd(), r))).filter(
  (f) => !EXCLUDED.some(([rx]) => rx.test(f)),
);

// COMMENTS STRIPPED BEFORE MATCHING, and this guard needed it for itself.
// `lib/describe-save-error.ts`'s docstring QUOTES the defect verbatim while
// explaining it, so widening the roots made the helper that FIXES this report
// as an offender. An assertion satisfied by a comment is the shape this repo
// keeps paying for; here it fires the other way, flagging correct code, which
// is how a gate gets weakened to shut it up.
function code(path: string): string {
  return readFileSync(path, "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");
}

// `err instanceof Error ? err.message` and its spellings, plus a bare
// `<ident>.message` fed to a state setter. Deliberately NOT anchored to `err`:
// the variable is named `e` and `error` elsewhere in this codebase.
const RENDERS_INTERNAL_MESSAGE =
  /instanceof\s+Error\s*(\?|\n\s*\?)\s*\w+\.message/;

describe("client-facing surfaces never render an internal error string", () => {
  it("finds the client surfaces at all", () => {
    // Fail closed. An empty sweep is "I could not look", and vitest reports a
    // zero-case `it.each` as a pass.
    expect(FILES.length).toBeGreaterThanOrEqual(30);
  });

  it("no file renders a caught error's own message", () => {
    const offenders = FILES.filter((f) =>
      RENDERS_INTERNAL_MESSAGE.test(code(f)),
    ).map((f) => f.slice(f.indexOf("src")));

    expect(
      offenders,
      `these client-facing files render a caught error's .message. Every proxy
error class is constructed as \`X proxy <status>\`, so this shows a client an
internal string. Use clientFacingError(err, "<generic fallback>"), which
returns the server's typed sentence when there is one.`,
    ).toEqual([]);
  });

  it("no surface sets its error copy straight from the caught value", () => {
    // THE INVERSE, and the predicate took two tries to state honestly.
    //
    // Deleting the offending expression without replacing it would satisfy
    // the assertion above by showing the client nothing at all. But the first
    // version of this demanded a call to `clientFacingError` or
    // `describeSaveError` BY NAME, and flagged four files that are correct:
    // `SignInForm` maps a refusal code through a `REFUSALS[...]` lookup --
    // the ideal pattern -- and `MessageThread` calls `describeMessagesError`,
    // a named helper that routes through `clientFacingError` one layer down.
    //
    // A gate that reports correct code is worse than one that reports
    // nothing: it gets weakened to shut it up. So the predicate is the actual
    // rule rather than a list of blessed function names -- copy must never be
    // the caught value itself.
    const offenders = FILES.filter((f) =>
      /set\w*(Error|State)\s*\(\s*(err|e|error)\s*[),]/.test(code(f)),
    ).map((f) => f.slice(f.indexOf("src")));

    expect(
      offenders,
      `these client-facing files set error state directly from the caught
value. Even where it renders as "[object Object]" rather than an internal
string, nothing there was written for a person to read.`,
    ).toEqual([]);
  });
});
