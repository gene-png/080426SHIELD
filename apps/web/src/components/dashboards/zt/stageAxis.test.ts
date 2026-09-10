import { describe, expect, it } from "vitest";

import { stageAxis } from "./stageAxis";

/**
 * #208: the maturity legend was CISA's four stages, hardcoded, under every
 * framework — so a DoD ZTRA client read their maturity against a four-stop
 * scale labelled with another framework's stage names. "Optimal" is not a DoD
 * stage at all: it is the same wrong label #125 removed from the intake UI,
 * still being rendered on the client's own results page.
 *
 * The bars were never wrong. `current_pct` / `target_pct` are normalised
 * server-side against `level_count(framework)`, so the geometry was right and
 * only the legend lied — which is why nothing looked broken and no test caught
 * it. A test that only checked the bar positions would still pass today.
 *
 * The expected values are derived from the SPEC rather than from the
 * implementation: `app/zt/maturity.py`'s `stage_label` / `level_count` are the
 * authority, and these are their outputs. Reading them out of `stageAxis`
 * itself would be the shape where a test and its subject agree by
 * construction.
 */
describe("stageAxis", () => {
  it("gives DoD ZTRA its own three-stage ladder", () => {
    expect(stageAxis("dod_ztra")).toEqual([
      "Not Started",
      "Target",
      "Advanced",
    ]);
  });

  it("never labels a DoD engagement with a CISA stage", () => {
    // The specific defect, asserted specifically. `Optimal` is the one that
    // cannot be explained away as a coincidence of wording.
    expect(stageAxis("dod_ztra")).not.toContain("Optimal");
    expect(stageAxis("dod_ztra")).not.toContain("Traditional");
    expect(stageAxis("dod_ztra")).not.toContain("Initial");
  });

  it("gives CISA ZTMM 2.0 its four stages", () => {
    expect(stageAxis("cisa_ztmm_2_0")).toEqual([
      "Traditional",
      "Initial",
      "Advanced",
      "Optimal",
    ]);
  });

  it("returns null for a framework it does not know, rather than a wrong scale", () => {
    // `ZtDashboardData.framework` is typed `string`, so the compiler cannot
    // rule this out. Rendering SOME axis for an unrecognised framework is the
    // defect being fixed, one framework further on: absent beats wrong,
    // because the bar geometry stays correct either way and a missing legend
    // is visible while a wrong one is not.
    expect(stageAxis("some_future_framework")).toBeNull();
    expect(stageAxis("")).toBeNull();
  });

  it("does not share an array instance between callers", () => {
    // Cheap, and it pins a real hazard: a caller that sorts or reverses the
    // returned axis in place would otherwise corrupt every later render.
    const a = stageAxis("dod_ztra");
    const b = stageAxis("dod_ztra");
    expect(a).toEqual(b);
    expect(a).not.toBe(b);
  });
});
