/**
 * The workspace must never ask the API for a stage the framework does not have.
 *
 * This is the regression half of #125. `normalizeTarget` was framework-blind --
 * `value === 2 || value === 3 || value === 4 ? value : 3` -- so a DoD
 * engagement whose client chose Stage 4 (reachable through the product's own
 * intake, which offered it) requested `target_stage=4`.
 *
 * That was survivable only while `analyze_gaps` CLAMPED an out-of-range target
 * and answered 200. Once it began refusing with a typed 422, the same request
 * started costing the consultant a panel.
 *
 * **THE ORIGINAL SENTENCE HERE HAS EXPIRED TWICE and is corrected rather than
 * deleted**, because this file is where someone checks what the refusal costs.
 * It said `refreshScoreAndGap` "runs both fetches under one `Promise.all`
 * whose rejection is swallowed, so the gap card AND the score card ... both
 * stayed blank, with nothing shown to the consultant". Neither half is true
 * now: `3933c46` (#292/#379) replaced the swallow with a recorded note, and
 * #185 replaced the `Promise.all` with `allSettled` keyed per panel. The score
 * card survives a gap refusal, and the consultant reads the 422's own
 * sentence.
 *
 * This is the same correction made at the copy of this paragraph in
 * `ZtWorkspace.tsx`'s `normalizeTarget` docstring. Two copies of one claim
 * expired together, which is the argument for the clamp being pinned HERE
 * rather than described in two places.
 *
 * What still justifies the clamp: the request should never be made at all.
 *
 * No backend test can see this: the API is behaving correctly. It is pinned
 * here or nowhere.
 */
import { describe, expect, it } from "vitest";

import { normalizeTarget } from "./ZtWorkspace";
import type { CatalogStage } from "@/lib/zt/types";

const s = (...ns: number[]): CatalogStage[] =>
  ns.map((n) => ({ stage: n, label: `Stage ${n}`, description: "" }));

// The real ladders, from `app/zt/maturity.py`: CISA_STAGES and DOD_STAGES.
const CISA = s(1, 2, 3, 4);
const DOD = s(1, 2, 3);

describe("normalizeTarget", () => {
  it("keeps a stage the framework really has", () => {
    // POSITIVE CONTROL: a CISA 4 is a real target and must survive untouched.
    // Without this, every assertion below is satisfied by a function that
    // always returns 3.
    expect(normalizeTarget(4, CISA)).toBe(4);
    expect(normalizeTarget(2, CISA)).toBe(2);
    expect(normalizeTarget(2, DOD)).toBe(2);
    expect(normalizeTarget(3, DOD)).toBe(3);
  });

  it("never returns a stage the framework lacks", () => {
    // THE DEFECT. DoD ZTRA ends at 3; the old function returned 4 here.
    expect(normalizeTarget(4, DOD)).toBe(3);
  });

  it("never returns a stage outside the ladder, for any stored value", () => {
    const ladders: Array<[string, CatalogStage[]]> = [
      ["cisa", CISA],
      ["dod", DOD],
    ];
    const stored = [null, undefined, 0, 1, 2, 3, 4, 5, 99, -1, 3.9, NaN];
    for (const [name, ladder] of ladders) {
      const allowed = ladder.map((x) => x.stage).filter((n) => n >= 2);
      for (const v of stored) {
        const out = normalizeTarget(v as number | null | undefined, ladder);
        expect(allowed, `${name} <- ${String(v)}`).toContain(out);
      }
    }
  });

  it("does not offer stage 1 as a target", () => {
    // Stage 1 is a starting point, not a goal; the dropdown starts at 2.
    expect(normalizeTarget(1, CISA)).toBe(3);
    expect(normalizeTarget(1, DOD)).toBe(3);
  });

  it("falls back to the engine default when the ladder is unavailable", () => {
    // Asking for a stage that cannot be checked is the case that cost two
    // blank cards, so an unknown ladder must not pass the stored value through.
    expect(normalizeTarget(4, null)).toBe(3);
    expect(normalizeTarget(4, undefined)).toBe(3);
    expect(normalizeTarget(4, [])).toBe(3);
  });

  it("uses the framework's own ceiling when 3 is not on the ladder", () => {
    // A hypothetical two-stage ladder: the default is not selectable, so the
    // highest real stage is the only honest answer. Guards the branch rather
    // than the framework.
    expect(normalizeTarget(4, s(1, 2))).toBe(2);
  });
});
