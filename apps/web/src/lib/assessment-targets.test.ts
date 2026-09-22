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
 * The cost of a source scan is that it is a grep and can only see the
 * spellings it knows. Stated rather than left implicit: `stage > 1` and
 * `stage >= MIN` where `MIN` is a fresh local constant both escape it. It is
 * a floor, not a census.
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
];

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
  });
});
