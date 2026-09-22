import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { MIN_TARGET_STAGE, MIN_TARGET_TIER } from "./assessment-targets";

/**
 * THE TARGET FLOOR HAS ONE HOME (#194).
 *
 * ## What this can and cannot prove
 *
 * There is no live defect to pin. All four sites spelled the same `2`, so a
 * test asserting they AGREE would have passed before this change and after
 * it, and would have proved nothing either way -- the enumeration-versus-
 * derivation defect turned into a test.
 *
 * What is checkable is the property the change actually establishes: that the
 * floor cannot be spelled anywhere but here. So this reads the consuming
 * files off disk and fails if a bare numeric comparison against a stage or
 * tier reappears. That assertion is red the moment someone re-hardcodes one,
 * which is the only way this can regress.
 *
 * ## Why a source scan rather than a behavioural test
 *
 * The defect is a DUPLICATION, and duplication has no runtime signature while
 * the copies agree. A behavioural test would have to set the copies to
 * different values to see anything -- which means editing the source, which
 * means it is testing an edit rather than the code. `CLAUDE.md` calls this
 * out: a test that supplies its own precondition from the thing under test
 * cannot fail.
 *
 * ## The residual, corrected -- it was wrong in BOTH directions
 *
 * This said: "`stage > 1` and `stage >= MIN` where `MIN` is a fresh local
 * constant both escape it." Both halves were wrong, and an inaccurate residual
 * is worse than none, because it is the sentence the next reader checks instead
 * of the regex.
 *
 * `stage > 1` IS caught -- the pattern allows `>` as well as `>=`, and the
 * evidence test below asserts exactly that, three lines from the sentence
 * denying it. The residual was understated in its own favour.
 *
 * What genuinely escapes, measured by running the pattern:
 *
 *     .filter((s) => s >= 2)                      no ladder noun beside the operator
 *     const MIN_TARGET_STAGE = 2;                 a local re-declaration
 *     value === 2 || value === 3 || value === 4    a membership test
 *     { value: 2, label: "Tier 2" }                a floor by OMISSION from a list
 *
 * The first is the sharp one: `normalizeTarget` in `ZtWorkspace.tsx` really is
 * written `.filter((s) => s >= MIN_TARGET_STAGE)`, mapping to numbers before
 * filtering, so the noun is gone by the time the comparison happens. That file
 * is in `CONSUMERS` below, which IMPLIES a coverage the comparison scan cannot
 * deliver for it. Two assertions now close that: a re-declaration detector, and
 * a positive check that every consumer still imports from this module -- the
 * second is what catches a site that re-hardcodes and drops the import, whatever
 * spelling it uses.
 *
 * The last two are the shapes that hid the other homes of this rule entirely:
 * `CsfWorkspace`'s membership test, and the three option lists in
 * `lib/intake/types.ts` that express the floor by starting at 2. Neither
 * contains a comparison, so no widening of a comparison pattern reaches them.
 * Those are #406; this file does not pretend to cover them.
 *
 * It is a floor, not a census -- but now an accurately described one.
 */

const WEB_SRC = join(process.cwd(), "src");

/**
 * The files that select a targetable level. DERIVED from the rule -- "every
 * surface that filters a catalog ladder down to what a client may target" --
 * and then listed, because there are four and a glob over `src` would sweep
 * in every unrelated numeric comparison in the bundle.
 *
 * If a fifth picker is added and not added here, this test says nothing about
 * it. That is the residual, and it is why the assertion below is phrased as
 * "no bare literal in THESE files" rather than "the floor has one home".
 */
const CONSUMERS = [
  "components/admin/zt/ZtWorkspace.tsx",
  "components/admin/zt/ZtGapList.tsx",
  "components/self-assessment/ZtSelfAssessment.tsx",
  "components/self-assessment/CsfSelfAssessment.tsx",
  // The fifth, added after review: `CsfWorkspace.normalizeTarget` stated the
  // floor as `value === 2 || value === 3 || value === 4` -- an operator, but
  // `===`, and no ladder noun beside it, so the comparison scan walked past it
  // while its ZT twin was wired in the same commit.
  "components/admin/csf/CsfWorkspace.tsx",
];

/** A local re-declaration of a floor this module owns: `MIN_TARGET_TIER = 2`. */
const REDECLARES_FLOOR = /\b(?:MIN_TARGET_STAGE|MIN_TARGET_TIER)\s*=\s*\d/;

/**
 * A floor stated as a MEMBERSHIP TEST, with no comparison operator beside a
 * ladder noun: `value === 2 || value === 3 || value === 4`. This is the shape
 * that hid `CsfWorkspace` from the original sweep entirely.
 */
const MEMBERSHIP_FLOOR = /===\s*\d+\s*\|\|\s*[\w.]+\s*===\s*\d+/;

/** The import that makes a consumer a consumer. */
const IMPORTS_FLOOR = /from\s+"@\/lib\/assessment-targets"/;

/** A bare numeric floor on a ladder: `stage >= 2`, `tier > 1`, `s.stage >= 3`. */
const BARE_NUMERIC_FLOOR = /\b(?:stage|tier)\s*>=?\s*\d/i;

function source(relative: string): string {
  return readFileSync(join(WEB_SRC, relative), "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");
}

describe("the target floor has one home (#194)", () => {
  it("exports a floor for both ladders", () => {
    // Fail closed: an import that silently resolved to `undefined` would make
    // every comparison below meaningless, and `undefined >= x` is false
    // rather than an error.
    expect(typeof MIN_TARGET_STAGE).toBe("number");
    expect(typeof MIN_TARGET_TIER).toBe("number");
  });

  it("finds the consuming files at all", () => {
    // An unreadable path would turn the assertion below into zero cases,
    // which vitest reports as a pass.
    for (const rel of CONSUMERS) {
      expect(
        source(rel).length,
        `${rel} is empty or unreadable`,
      ).toBeGreaterThan(100);
    }
  });

  it("no picker spells the floor as a bare literal", () => {
    // THE ASSERTION. Red the moment a `.filter((s) => s.stage >= 2)` comes
    // back, which is exactly how this regresses -- someone adds a picker by
    // copying the line next to it.
    const offenders = CONSUMERS.filter((rel) =>
      BARE_NUMERIC_FLOOR.test(source(rel)),
    );

    expect(
      offenders,
      `these files compare a stage or tier against a bare number. The lowest
targetable level is a product rule with one home: import MIN_TARGET_STAGE or
MIN_TARGET_TIER from "@/lib/assessment-targets". A second spelling cannot
disagree loudly -- a controlled <select> whose value is no longer in its
options renders blank, with no error.`,
    ).toEqual([]);
  });

  it("every consumer still imports the floor from this module", () => {
    // THE POSITIVE CHECK, and it is what covers the spelling the comparison
    // scan cannot see. `ZtWorkspace.normalizeTarget` maps to numbers before
    // filtering -- `.filter((s) => s >= MIN_TARGET_STAGE)` -- so a revert to
    // `>= 2` there carries no ladder noun and matches nothing above.
    //
    // A site that re-hardcodes the floor has to stop importing it, or keep a
    // dead import. This catches the first case whatever spelling it uses, which
    // is strictly more than widening the comparison regex could achieve.
    const missing = CONSUMERS.filter((rel) => !IMPORTS_FLOOR.test(source(rel)));

    expect(
      missing,
      `these files are listed as consumers of the target floor but no longer
import it from "@/lib/assessment-targets". Either they re-hardcoded the floor --
which the comparison scan cannot always see, because a filter over mapped
numbers carries no stage/tier token -- or they are no longer consumers and this
list is stale. Both need a human.`,
    ).toEqual([]);
  });

  it("no file re-declares a floor this module owns", () => {
    // The other escape the comparison scan misses: `const MIN_TARGET_STAGE = 2`
    // put back locally. The import line carries no `=`, so this cannot fire on
    // a legitimate consumer.
    const offenders = CONSUMERS.filter((rel) =>
      REDECLARES_FLOOR.test(source(rel)),
    );

    expect(
      offenders,
      `these files re-declare MIN_TARGET_STAGE or MIN_TARGET_TIER locally. That
is the duplication #194 removed, reintroduced under the same name -- which reads
as correct at every call site while disagreeing with every other consumer.`,
    ).toEqual([]);
  });

  it("no picker states the floor as a membership test", () => {
    // THE SHAPE THAT HID `CsfWorkspace` ENTIRELY. `value === 2 || value === 3
    // || value === 4` has an operator but it is `===`, with no ladder noun
    // beside it, so the comparison scan above cannot see it -- which is why
    // that file's floor stayed hardcoded while its ZT twin was wired in the
    // same commit.
    const offenders = CONSUMERS.filter((rel) =>
      MEMBERSHIP_FLOOR.test(source(rel)),
    );

    expect(
      offenders,
      `these files enumerate the allowed levels instead of comparing against the
floor. Use >= MIN_TARGET_STAGE / MIN_TARGET_TIER: a membership test states the
floor in a form no comparison sweep can find, and it has to be edited in full
every time the ladder changes.`,
    ).toEqual([]);
  });

  it("detects the shape it is scanning for", () => {
    // THE DETECTOR'S OWN EVIDENCE. Without this, a regex that matched nothing
    // would report every file clean forever -- the guard reporting success
    // for having looked at nothing.
    expect(BARE_NUMERIC_FLOOR.test(".filter((s) => s.stage >= 2)")).toBe(true);
    expect(
      BARE_NUMERIC_FLOOR.test("catalog.tiers.filter((t) => t.tier >= 2)"),
    ).toBe(true);
    expect(BARE_NUMERIC_FLOOR.test("stage > 1")).toBe(true);
    // And leaves the derived spelling alone, or it would flag the fix itself.
    expect(BARE_NUMERIC_FLOOR.test("(s) => s.stage >= MIN_TARGET_STAGE")).toBe(
      false,
    );
    expect(BARE_NUMERIC_FLOOR.test("(t) => t.tier >= MIN_TARGET_TIER")).toBe(
      false,
    );

    // AND THE TWO NEW DETECTORS' OWN EVIDENCE. Each must fire on the shape it
    // exists for and stay silent on the legitimate form, or it is a detector
    // that reports every file clean forever.
    expect(REDECLARES_FLOOR.test("const MIN_TARGET_STAGE = 2;")).toBe(true);
    expect(REDECLARES_FLOOR.test("const MIN_TARGET_TIER = 2;")).toBe(true);
    expect(
      REDECLARES_FLOOR.test(
        'import { MIN_TARGET_STAGE } from "@/lib/assessment-targets";',
      ),
    ).toBe(false);

    expect(
      IMPORTS_FLOOR.test(
        'import { MIN_TARGET_TIER } from "@/lib/assessment-targets";',
      ),
    ).toBe(true);
    expect(IMPORTS_FLOOR.test('import { x } from "@/lib/zt/types";')).toBe(
      false,
    );

    expect(
      MEMBERSHIP_FLOOR.test("value === 2 || value === 3 || value === 4"),
    ).toBe(true);
    // Two unrelated equality checks in one file are not a membership test.
    expect(MEMBERSHIP_FLOOR.test("if (a === 1) {} if (b === 2) {}")).toBe(
      false,
    );
  });
});
