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
  // Found by WIDENING THE PATTERN BELOW, not by reading this list. It is the
  // exact twin of the risk entry directly above -- `proxyMessage` ends
  // `err instanceof Error && err.message ? err.message : fallback` -- and it
  // was in scope and matching nothing, so the suite was green by regex
  // accident over a live instance of the shape this file exists to forbid.
  //
  // Derived rather than assumed: `grep -rln "lib/tech_debt/client" src`
  // returns DeliverableCard, EditableCapabilityTable,
  // SecurityClassificationQueue and TechDebtWorkspace -- every one under
  // `components/admin/`. A consultant, not a client, so it takes the same
  // disposition as risk: filed, not swept in here.
  [
    /[\/]lib[\/]tech_debt[\/]client\.ts$/,
    "proxyMessage is consumed only by components/admin/** (#365)",
  ],
  // The third twin, and also found by running a widened pattern rather than
  // by reading this list. `getActiveClientId` throws
  // `Could not read the active client (${res.status}).` -- an HTTP status as
  // copy. Its own docstring opens "The admin client switcher's active
  // tenant", and `grep -rn "active-client" src` gives its importers as
  // `components/admin/DeliverablesTable.tsx` and a re-export from
  // `lib/risk/client.ts`, itself already excluded above as admin-only. Same
  // disposition, and the file carries no `.message` shape, so nothing else
  // here loses coverage by excluding it.
  [
    /[\/]lib[\/]active-client\.ts$/,
    "getActiveClientId is consumed only by admin surfaces (#365)",
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

// THE CAUGHT VALUE'S OWN `.message`, in any spelling.
//
// This used to be `/instanceof\s+Error\s*(\?|\n\s*\?)\s*\w+\.message/` -- the
// TERNARY spelling and nothing else -- under a comment claiming it also
// covered "a bare `<ident>.message` fed to a state setter". It did not:
// `setError(err.message)` has no `instanceof`, so it matched neither this
// pattern nor the setter pattern below, whose `[),]` ends at the identifier.
// A claim in a comment, with no assertion under it, in the guard whose whole
// job is to be the assertion.
//
// Worse, the `&&` spelling escaped too, and a live instance was sitting in the
// guard's own in-scope set: `lib/tech_debt/client.ts` ends `proxyMessage` with
// `err instanceof Error && err.message ? err.message : fallback`. The suite
// was green because of how the pattern was SPELLED, not because the set was
// clean.
//
// So the predicate is now the SHAPE rather than one syntax: a caught value's
// `.message`, read directly. The lookbehind is what keeps it honest -- a
// payload read is `body.error?.message` / `payload?.error?.message`, where
// `error` is preceded by a dot, and flagging those would report correct code,
// which is how a gate gets weakened to shut it up.
//
// Deliberately NOT anchored to `err`: the variable is named `e` and `error`
// elsewhere in this codebase.
const RENDERS_INTERNAL_MESSAGE = /(?<![.\w$])(err|e|error)\s*\??\.message\b/;

// AN HTTP STATUS INTERPOLATED INTO A SENTENCE. The second half of the same
// rule: "Upload failed (413)" tells a client nothing they can act on, and
// this PR deleted exactly that shape from `lib/messages/client.ts` -- a bare
// `Request failed (<status>).` -- while leaving `Dropzone`'s
// `Upload failed (${err.status})` standing in a file it was editing. An
// unstated exemption reads as an oversight to everyone who finds it later.
//
// NO NEWLINES ANYWHERE IN IT, and that is the whole difficulty. The first
// version allowed them, so `[^`]*` walked from a backtick in one expression,
// across unrelated lines, to a `${` in another -- and reported
// `SessionExpiryWarning.tsx` as an offender over the Tailwind class
// `border-status-danger-fg`, which is a double-quoted string that contains
// neither a template literal nor an HTTP status. A gate that reports correct
// code is worse than one that reports nothing, because it gets weakened to
// shut it up. Found by running it, not by reading it.
const STATUS_AS_COPY = /`[^`\n]*\$\{[^}\n]*status[^}\n]*\}[^`\n]*`/;

// The one legitimate interpolation of a status, and it is legitimate BY
// CONSTRUCTION rather than by judgement: `super(\`ZT proxy ${status}\`)` is
// the internal label every proxy error class carries, and the premise of this
// whole file is that no surface renders it. Stripped rather than excluded per
// file, because every `lib/*/client.ts` has one and a file list would grow on
// the tenth client and say nothing about why.
function codeWithoutErrorLabels(path: string): string {
  return code(path).replace(/super\(`[^`]*`\)/g, "");
}

/**
 * THE PATTERN'S OWN EVIDENCE, because a sweep is only as good as its predicate
 * and the previous predicate reported clean over a live instance.
 *
 * Every string below is a REAL line from this repo, not an invention — the
 * offenders are the spellings the old pattern missed and the ones it caught,
 * and the acceptable ones are the payload reads a widened pattern would
 * wrongly flag. A pattern tested only against strings its author wrote to
 * match it agrees with itself by construction, which is the fixture defect
 * `CLAUDE.md` names; these came off `grep -rn "\.message" src`.
 */
describe("the offending-shape pattern", () => {
  it.each([
    // The ternary, which the old pattern caught. components/admin/DeliverableCard.tsx
    'return err instanceof Error ? err.message : "Request failed.";',
    // The `&&` spelling, which it did not. lib/tech_debt/client.ts
    "return err instanceof Error && err.message ? err.message : fallback;",
    // The bare setter, claimed by the old comment and implemented by nothing.
    "setError(err.message);",
    // The other two identifiers this codebase uses for a caught value.
    'return e instanceof Error ? e.message : "Readiness probe failed.";',
    "setLoadError(error.message);",
  ])("flags %j", (line) => {
    expect(RENDERS_INTERNAL_MESSAGE.test(line)).toBe(true);
  });

  it.each([
    // Payload reads. `error` here is a FIELD of the server's envelope, not the
    // caught value, and flagging these would report correct code.
    'setError(body.error.message ?? "Choose a stronger password.");',
    "const message = body.error?.message;",
    "payload?.error?.message ??",
    "const enveloped = payload.error?.message;",
    // Not the caught value at all: an upload row, and a save-status union.
    "{it.message}",
    "Couldn&apos;t save: {state.message}",
  ])("leaves %j alone", (line) => {
    expect(RENDERS_INTERNAL_MESSAGE.test(line)).toBe(false);
  });

  it.each([
    // The line this PR removed from Dropzone, and the one it removed from
    // lib/messages/client.ts. Both are what the sweep is for.
    "`Upload failed (${err.status})`",
    "`Request failed (${res.status}).`",
    "`Could not read the active client (${res.status}).`",
  ])("flags %j as a status in copy", (line) => {
    expect(STATUS_AS_COPY.test(line)).toBe(true);
  });

  it.each([
    // The Tailwind class the FIRST version of this pattern flagged, by
    // walking a `[^`]*` across newlines out of one expression and into
    // another. It is a double-quoted string and contains no status.
    '? "border-status-danger-fg bg-surface-card"',
    // A status compared, not rendered.
    "if (err.status === 404) return null;",
  ])("leaves %j alone as a status in copy", (line) => {
    expect(STATUS_AS_COPY.test(line)).toBe(false);
  });

  it("does not flag a proxy class's own constructor label", () => {
    // Stripped by `codeWithoutErrorLabels`, not by the pattern -- so this
    // asserts the STRIPPER, which is the part that could silently stop
    // working and leave nine `lib/*/client.ts` files reporting as offenders.
    const label = "    super(`ZT proxy ${status}`);";
    expect(STATUS_AS_COPY.test(label)).toBe(true);
    expect(STATUS_AS_COPY.test(label.replace(/super\(`[^`]*`\)/g, ""))).toBe(
      false,
    );
  });
});

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

  it("no surface puts an HTTP status in a sentence", () => {
    const offenders = FILES.filter((f) =>
      STATUS_AS_COPY.test(codeWithoutErrorLabels(f)),
    ).map((f) => f.slice(f.indexOf("src")));

    expect(
      offenders,
      `these client-facing files interpolate an HTTP status into copy. A client
cannot act on "(413)"; it is the same shape as an internal proxy label and
core principle 2 forbids it for the same reason. Use clientFacingError(err,
"<generic fallback>"), which returns the server's typed sentence when there
is one and the fallback otherwise.`,
    ).toEqual([]);
  });
});
