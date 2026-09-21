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

const ROOTS = ["src/components/self-assessment", "src/components/intake"];

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

const FILES = ROOTS.flatMap((r) => walk(join(process.cwd(), r)));

// `err instanceof Error ? err.message` and its spellings, plus a bare
// `<ident>.message` fed to a state setter. Deliberately NOT anchored to `err`:
// the variable is named `e` and `error` elsewhere in this codebase.
const RENDERS_INTERNAL_MESSAGE =
  /instanceof\s+Error\s*(\?|\n\s*\?)\s*\w+\.message/;

describe("client-facing surfaces never render an internal error string", () => {
  it("finds the client surfaces at all", () => {
    // Fail closed. An empty sweep is "I could not look", and vitest reports a
    // zero-case `it.each` as a pass.
    expect(FILES.length).toBeGreaterThanOrEqual(10);
  });

  it("no file renders a caught error's own message", () => {
    const offenders = FILES.filter((f) =>
      RENDERS_INTERNAL_MESSAGE.test(readFileSync(f, "utf8")),
    ).map((f) => f.slice(f.indexOf("src")));

    expect(
      offenders,
      `these client-facing files render a caught error's .message. Every proxy
error class is constructed as \`X proxy <status>\`, so this shows a client an
internal string. Use clientFacingError(err, "<generic fallback>"), which
returns the server's typed sentence when there is one.`,
    ).toEqual([]);
  });

  it("the surfaces that report an error use the shared helper", () => {
    // The inverse. Deleting the offending expression without replacing it
    // would satisfy the assertion above by showing the client nothing at all.
    const reportsErrors = FILES.filter((f) =>
      /set\w*Error\(|setSaveState\(/.test(readFileSync(f, "utf8")),
    );
    expect(reportsErrors.length).toBeGreaterThanOrEqual(4);

    const withoutHelper = reportsErrors
      .filter((f) => {
        const src = readFileSync(f, "utf8");
        return !/clientFacingError\(|describeSaveError\(/.test(src);
      })
      .map((f) => f.slice(f.indexOf("src")));

    expect(
      withoutHelper,
      `these client-facing files set an error state without going through a
copy helper, so whatever they show was not checked against the internal-string
rule.`,
    ).toEqual([]);
  });
});
