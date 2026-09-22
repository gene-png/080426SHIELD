import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * No CLIENT-facing surface renders an internal string (#318).
 *
 * Two shapes, and they are the same rule: a caught error's own `.message`,
 * and an HTTP status interpolated into a sentence. Neither was written for a
 * person to read.
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
 * `components/admin/**` is DELIBERATELY out of scope and it is NOT clean. A
 * Kentro consultant reading "CSF proxy 409" is a real defect and a different
 * tier from a client reading it, so it is filed as #365 (open, tier-3,
 * post-mvp) rather than swept in here -- and named here so the exemption reads
 * as a decision rather than an oversight.
 *
 * **Deleting the exclusions gives you CANDIDATES, not a defect list**, and this
 * paragraph used to call that "a better statement of the fact than a number
 * that goes stale". It is better than a stale number and it is not a fact:
 * measured over `src` in node, the status assertion alone reported six correct
 * admin lines before the narrowing beside `STATUS_AS_COPY` dropped them.
 * Whoever sizes #365 from the raw list will investigate non-defects, so read
 * the output as a starting set and check each one.
 *
 * The narrowing is the reason the number is no longer written here: it changed
 * the answer, which is what a count in prose cannot survive.
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

//: Each exclusion named with its reason. The `lib/` entries are admin-only by
//: their CONSUMERS, which a path does not say, so each one carries the grep
//: that establishes it rather than being gestured at. (This comment used to
//: say "the two lib helpers" and there are now three -- a count sitting two
//: lines above the list it counts, which is the form `CLAUDE.md`'s first rule
//: for numbers says to delete rather than update.)
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

const ALL = SEARCH_ROOTS.flatMap((r) => walk(join(process.cwd(), r)));
const NOT_EXCLUDED = ALL.filter((f) => !EXCLUDED.some(([rx]) => rx.test(f)));

// A PATH DOES NOT DECIDE WHO RENDERS A COMPONENT, so the `admin/` exclusion is
// re-opened for anything a client surface actually imports.
//
// The exclusion above says "a consultant, not a client". That reason is FALSE
// for three files under `components/admin/`:
//
//     components/self-assessment/CsfSelfAssessment.tsx
//       -> @/components/admin/csf/CsfQuestionnaire  -> ./TierPicker
//     components/self-assessment/ZtSelfAssessment.tsx
//       -> @/components/admin/zt/ZtStagePicker
//
// All of them render on `app/self-assessment/[serviceId]/page.tsx`, which
// gates on `if (!session)` and nothing else -- so a CLIENT's browser renders
// them. They are clean today (no `.message`, no `catch`, no `throw`, no
// status), which is why nothing failed; the hole is that the first
// `setError(err.message)` added to `CsfQuestionnaire.tsx` reaches a client and
// this guard reports clean. That is the same two-directory-list failure the
// comment above records, one level up: the first version narrowed by DIRECTORY
// and this one narrowed by directory again, under a reason about AUDIENCE.
//
// Derived, not listed. `ADMIN_RENDERED_BY_CLIENT_SURFACES` follows imports
// transitively from the non-admin in-scope files, so moving a component into
// `admin/` -- or adding a fourth -- is covered on the day it happens rather
// than the day someone remembers this file. The three names above are in a
// comment as the worked example; nothing reads them.
const SRC = join(process.cwd(), "src");

function importTargets(file: string): string[] {
  const body = readFileSync(file, "utf8");
  const out: string[] = [];
  // `from "..."` covers static imports and re-exports; `import("...")` covers
  // the dynamic form, which `next/dynamic` call sites use.
  for (const m of body.matchAll(/(?:from|import)\s*\(?\s*["']([^"']+)["']/g)) {
    const spec = m[1];
    if (spec.startsWith("@/")) out.push(join(SRC, spec.slice(2)));
    else if (spec.startsWith(".")) out.push(join(dirname(file), spec));
  }
  return out;
}

function resolveModule(base: string): string | null {
  for (const cand of [
    base,
    `${base}.ts`,
    `${base}.tsx`,
    join(base, "index.ts"),
    join(base, "index.tsx"),
  ]) {
    try {
      if (statSync(cand).isFile()) return cand;
    } catch {
      // Not a file on disk: a package import, a type-only path alias, or an
      // extension this guard does not read. Skipped rather than thrown -- but
      // NOT silently, because the reachable-set assertion below fails loudly
      // if resolution stops working altogether.
    }
  }
  return null;
}

function reachableFrom(seeds: string[]): Set<string> {
  const seen = new Set<string>();
  const queue = [...seeds];
  while (queue.length) {
    const file = queue.pop() as string;
    for (const target of importTargets(file)) {
      const resolved = resolveModule(target);
      if (resolved === null || seen.has(resolved)) continue;
      seen.add(resolved);
      queue.push(resolved);
    }
  }
  return seen;
}

const REACHABLE_FROM_CLIENT_SURFACES = reachableFrom(NOT_EXCLUDED);
const ADMIN_RENDERED_BY_CLIENT_SURFACES = ALL.filter(
  (f) =>
    EXCLUDED.some(([rx]) => rx.test(f)) &&
    REACHABLE_FROM_CLIENT_SURFACES.has(f),
);

const FILES = [...NOT_EXCLUDED, ...ADMIN_RENDERED_BY_CLIENT_SURFACES];

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
//
// THE SECOND ALTERNATIVE EXISTS BECAUSE THE LOOKBEHIND CANNOT SEE PAST A CAST.
// In `(err as Error).message` the character before `.message` is `)`, so the
// first alternative never fires -- the identifier it needs is inside the
// parentheses. That is the TypeScript idiom for exactly this operation, so the
// gap was the likeliest way in.
//
// Added while NOTHING has to change: `(err|e|error) as` returns no matches
// anywhere under `src`, so this widens the net over an empty population and
// cannot be flagging correct code today. The cast of a non-caught value --
// `(payload as Envelope).message` -- stays clear, because the alternative
// anchors on the three caught-value identifiers rather than on the parenthesis.
const RENDERS_INTERNAL_MESSAGE =
  /(?<![.\w$])(err|e|error)\s*\??\.message\b|\((?:err|e|error)\s+as\s+[^)]*\)\s*\??\.message\b/;

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
//
// TWO NARROWINGS, DERIVED FROM THE TWO SHAPES THAT SLIPPED THROUGH, not from a
// list of files to skip. `[^}\n]*status[^}\n]*` matched any identifier
// CONTAINING the word and any template at all, so over `src` it reported six
// correct lines: four React keys (`` `${assessment?.status ?? ""}:${...}` ``
// in three workspaces and `list?.status` in a fourth) and two in
// `attack/StatusBadge.tsx` -- a `className` and a `title`, both built from
// `TONE[status]` / `LABEL[status]`.
//
//  1. the interpolation must read a `.status` PROPERTY, which drops
//     `${TONE[status]}` -- a lookup keyed by a variable that happens to be
//     called `status`;
//  2. the literal must carry a letter OUTSIDE its interpolations, i.e. be
//     prose, which drops `` `${a}:${b}` `` React keys. `hasProseOutsideHoles`
//     is that half, because a regex cannot express "outside every `${}`".
//
// Measured over `src/components` and `src/lib` with the real JS regex in node:
// 28 lines before, 22 after, and the six dropped are exactly the six above.
// **The first attempt to check this used `grep -rnE` and was worthless**: in
// POSIX ERE `[^`\n]` excludes the LETTER n, not a newline, so the grep silently
// disagreed with the JavaScript this file actually runs and "disproved" a real
// finding. Test a JS regex with JS.
//
// RESIDUAL, stated because narrowing 1 bought the false-positive fix with a
// false negative: a status held in a LOCAL whose name contains the word --
// `` `Upload failed (${statusCode})` `` -- was caught by the old pattern and is
// not caught by this one. No site spells it that way today. The error direction
// is the acceptable one: this can only under-report, and a gate that reports
// correct code is the failure that gets it deleted. The `${st}` form escaped
// both versions, so it is not a regression, just a limit.
//
// Also a limit of the regex rather than a decision: `[^}\n]*` cannot cross a
// `}`, so a hole containing an inline type literal --
// `${(err as { status?: number }).status}` -- does not match. Found by writing
// exactly that as a red-on-revert mutation and watching the check stay green,
// which read as "the pattern regressed" until the mutation was read back.
const STATUS_AS_COPY = /`[^`\n]*\$\{[^}\n]*\??\.status[^}\n]*\}[^`\n]*`/;

function hasProseOutsideHoles(literal: string): boolean {
  return /[A-Za-z]/.test(literal.replace(/\$\{[^}\n]*\}/g, ""));
}

// EVERY match, not the first. A `source.match(...)` here would return only the
// leading hit, so a file whose first status template is a React key and whose
// second is real copy would report clean -- the narrowing above quietly
// becoming a way to hide the thing it exists to find. `\n` cannot appear inside
// a match, so scanning line by line is equivalent and is what the measurement
// in the comment above counted.
const STATUS_AS_COPY_ALL = new RegExp(STATUS_AS_COPY.source, "g");

function statusAsCopy(source: string): boolean {
  for (const m of source.matchAll(STATUS_AS_COPY_ALL)) {
    if (hasProseOutsideHoles(m[0])) return true;
  }
  return false;
}

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
    // The CAST spelling, which the lookbehind alone cannot reach: the
    // character before `.message` is `)`. No site uses it today, which is why
    // it is safe to pin now.
    "setError((err as Error).message);",
    "return (e as Error).message;",
    "const m = (error as ApiError)?.message;",
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
    // A cast of something that is NOT a caught value. The cast alternative
    // anchors on the three identifiers, not on the parenthesis, so this stays
    // clear -- pinned because anchoring on `)` was the tempting shortcut.
    "const m = (payload as Envelope).message;",
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
    expect(statusAsCopy(line)).toBe(true);
  });

  it.each([
    // The Tailwind class the FIRST version of this pattern flagged, by
    // walking a `[^`]*` across newlines out of one expression and into
    // another. It is a double-quoted string and contains no status.
    '? "border-status-danger-fg bg-surface-card"',
    // A status compared, not rendered.
    "if (err.status === 404) return null;",
    // THE SIX REAL LINES THE SECOND VERSION FLAGGED, all correct code, all
    // found by running the pattern over `src` in node rather than by reading
    // it. Without these the narrowing is a claim; with them it is pinned, and
    // a future widening that reinstates any of them goes red here first.
    //
    // A lookup keyed by a variable called `status` -- attack/StatusBadge.tsx.
    "      className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] font-semibold ${TONE[status]}`}",
    "      title={`Assigned ${LABEL[status].toLowerCase()}, held out of the coverage score`}",
    // React keys: a `.status` READ, but no prose outside the holes. Three
    // workspaces spell it with `assessment`, TechDebtWorkspace with `list`.
    '    `${assessment?.status ?? ""}:${assessment?.version ?? ""}`,',
    '    `${list?.status ?? ""}:${list?.version ?? ""}`,',
  ])("leaves %j alone as a status in copy", (line) => {
    expect(statusAsCopy(line)).toBe(false);
  });

  it("reads EVERY status template in a file, not just the first", () => {
    // The narrowing introduced a way to hide a defect: if the scan stopped at
    // the first match, a file whose leading status template is a React key
    // would report clean over real copy below it. That is the exact ordering
    // in three of the four workspaces, so it is not hypothetical.
    const keyThenCopy =
      '    `${assessment?.status ?? ""}:${assessment?.version ?? ""}`,\n' +
      "      `Request failed (${err.status}).`";
    expect(statusAsCopy(keyThenCopy)).toBe(true);
    // And the reverse order, so this pins the scan rather than the ordering.
    const copyThenKey =
      "      `Request failed (${err.status}).`\n" +
      '    `${assessment?.status ?? ""}:${assessment?.version ?? ""}`,';
    expect(statusAsCopy(copyThenKey)).toBe(true);
  });

  it("does not flag a proxy class's own constructor label", () => {
    // WHICH MECHANISM EXCLUDES IT CHANGED, and this test asserted the wrong one
    // until it went red. Every one of the nine labels is
    // `super(\`X proxy ${status}\`)` -- a bare CONSTRUCTOR PARAMETER named
    // `status`, not a `.status` read -- so narrowing 1 excludes them and
    // `codeWithoutErrorLabels` is no longer what does it. The old version
    // asserted the label matched and that the stripper removed it; the first
    // half is now false.
    expect(statusAsCopy("    super(`ZT proxy ${status}`);")).toBe(false);

    // THE STRIPPER IS STILL LOAD-BEARING, for the spelling nobody has written
    // yet. Kept rather than deleted, and pinned here so "unused" is a
    // measurement instead of a guess: a label built from a response object
    // would match the narrowed pattern, and only the stripper stops it.
    const propertyLabel = "    super(`ZT proxy ${res.status}`);";
    expect(statusAsCopy(propertyLabel)).toBe(true);
    expect(statusAsCopy(propertyLabel.replace(/super\(`[^`]*`\)/g, ""))).toBe(
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

  it("resolves imports at all, so the admin re-inclusion is not vacuous", () => {
    // THE SELECTOR'S OWN COUNT. `resolveModule` returns null for anything it
    // cannot find on disk, so a broken alias, a moved `src/`, or a change to
    // the import syntax it matches would make `reachableFrom` return an empty
    // set -- and every admin file would drop back out of scope with the suite
    // still green. Indistinguishable from "no admin file is client-rendered",
    // which is the answer a reader wants to be true.
    //
    // Asserted on the REACHABLE set rather than on the admin subset, on
    // purpose: moving those components out of `admin/` is a legitimate fix
    // that empties the subset, and a test that went red for it would punish
    // the repair.
    expect(REACHABLE_FROM_CLIENT_SURFACES.size).toBeGreaterThanOrEqual(20);
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
      statusAsCopy(codeWithoutErrorLabels(f)),
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
