// @vitest-environment node
import { fileURLToPath } from "node:url";

import { ESLint, Linter } from "eslint";
import { describe, expect, it } from "vitest";

// The block `eslint.config.js` installs, imported rather than restated, so the
// test and the gate cannot drift apart.
const intlTimeZone = require("../../eslint/intl-timezone.js");

/**
 * The gate: every `Intl.DateTimeFormat` in product code names its zone. A
 * formatter without one uses the VIEWER's zone, and the released-date badge
 * read as different days to different readers that way. A gate scoped to the one shared
 * formatter would have been green through both reports, because ATT&CK had a
 * private copy -- so this is a rule over every construction, not a check of
 * one file.
 */

function problems(code: string): string[] {
  const linter = new Linter({ configType: "flat" });
  return linter
    .verify(code, [
      { languageOptions: { ecmaVersion: 2022, sourceType: "module" } },
      { rules: intlTimeZone.rules },
    ])
    .map((m) => m.message);
}

describe("the Intl.DateTimeFormat time-zone rule", () => {
  it("passes a formatter that names its zone", () => {
    expect(
      problems(
        `new Intl.DateTimeFormat("en-US", { day: "numeric", timeZone: "UTC" });`,
      ),
    ).toEqual([]);
  });

  it("refuses one with options but no zone", () => {
    expect(
      problems(`new Intl.DateTimeFormat("en-US", { day: "numeric" });`),
    ).toHaveLength(1);
  });

  it("refuses one with no options at all", () => {
    expect(problems(`new Intl.DateTimeFormat("en-US");`)).toHaveLength(1);
  });

  it("refuses the call form, without `new`", () => {
    expect(
      problems(`Intl.DateTimeFormat("en-US", { day: "numeric" });`),
    ).toHaveLength(1);
  });

  it("refuses options passed through a variable, which it cannot see into", () => {
    // Fail closed: a zone it cannot SEE is a zone it cannot vouch for.
    expect(
      problems(
        `const o = { timeZone: "UTC" }; new Intl.DateTimeFormat("en-US", o);`,
      ),
    ).toHaveLength(1);
  });

  it("names the remedy in its message", () => {
    expect(problems(`new Intl.DateTimeFormat("en-US");`)[0]).toMatch(
      /timeZone/,
    );
  });

  it("leaves other Intl formatters alone", () => {
    expect(problems(`new Intl.NumberFormat("en-US");`)).toEqual([]);
  });
});

// THE WIRING, through the real config: the tests above import the rule module
// directly, so they stay green if `eslint.config.js` stops installing it.
describe("eslint.config.js installs the rule", () => {
  const cwd = fileURLToPath(new URL("../..", import.meta.url));
  const unpinned = `export const F = new Intl.DateTimeFormat("en-US", { day: "numeric" });
`;

  it("refuses an unpinned formatter in product code", async () => {
    const [result] = await new ESLint({ cwd }).lintText(unpinned, {
      filePath: "src/components/Example.tsx",
    });
    expect(
      result.messages.filter((m) => m.ruleId === "no-restricted-syntax"),
    ).toHaveLength(1);
  }, 60_000);

  it("leaves a test file alone", async () => {
    const [result] = await new ESLint({ cwd }).lintText(unpinned, {
      filePath: "src/components/Example.test.tsx",
    });
    expect(
      result.messages.filter((m) => m.ruleId === "no-restricted-syntax"),
    ).toEqual([]);
  }, 60_000);
});
