/**
 * The target pickers DERIVE their floor; they do not restate it (#406).
 *
 * ## Why the obvious test would be the #72 shape
 *
 * `expect(CSF_TARGET_TIERS[0].value).toBe(2)` passes identically against the
 * derivation and against the hardcoded `[{value: 2}, {value: 3}, {value: 4}]`
 * it replaced. It pins today's NUMBERS, which is worth having and is the
 * second half of this file — but it can never see the thing the change was
 * for, because the two implementations agree on every observable until the
 * constant moves.
 *
 * So the first half MOVES THE CONSTANT. `vi.doMock` replaces
 * `@/lib/assessment-targets` with a raised floor and the module is imported
 * fresh; the lists must follow. Put the literal arrays back and these go red.
 *
 * ## Why a raised floor rather than a lowered one
 *
 * Lowering to 1 would also discriminate, and it would be the weaker choice:
 * every array here already ends where its ladder ends, so a lower floor only
 * adds entries at the front. Raising to 3 removes one from CSF and CISA and
 * takes DoD down to a single option — which is where a `<select>` with a
 * stale hardcoded list would silently offer a stage the API now refuses, the
 * blank-`selectedIndex` failure `assessment-targets.ts` records.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { MIN_TARGET_STAGE, MIN_TARGET_TIER } from "@/lib/assessment-targets";
import { clientFacingError } from "@/lib/describe-save-error";

afterEach(() => {
  vi.resetModules();
  vi.doUnmock("@/lib/assessment-targets");
});

async function optionsWithFloor(floor: number) {
  vi.resetModules();
  vi.doMock("@/lib/assessment-targets", () => ({
    MIN_TARGET_STAGE: floor,
    MIN_TARGET_TIER: floor,
  }));
  return await import("./types");
}

describe("the floor is derived, not restated", () => {
  it("drops CSF tiers below a raised floor", async () => {
    const { CSF_TARGET_TIERS } = await optionsWithFloor(3);
    expect(CSF_TARGET_TIERS.map((t) => t.value)).toEqual([3, 4]);
  });

  it("drops ZT stages below a raised floor, in BOTH frameworks", async () => {
    const { ZT_TARGET_STAGES } = await optionsWithFloor(3);
    expect(ZT_TARGET_STAGES.zero_trust_cisa.map((s) => s.value)).toEqual([
      3, 4,
    ]);
    expect(ZT_TARGET_STAGES.zero_trust_dod.map((s) => s.value)).toEqual([3]);
  });

  it("keeps the labels attached to the values they survive with", async () => {
    // A filter that returned bare numbers, or that re-indexed the array, would
    // satisfy the two assertions above. The <option> text is what a client
    // reads, so pin that it still belongs to its own value.
    const { CSF_TARGET_TIERS } = await optionsWithFloor(3);
    expect(CSF_TARGET_TIERS[0]).toEqual({
      value: 3,
      label: "Tier 3 · Repeatable",
    });
  });
});

describe("what the pickers offer today", () => {
  it("offers every CSF tier from the floor to the top of the ladder", async () => {
    const { CSF_TARGET_TIERS } = await import("./types");
    expect(CSF_TARGET_TIERS.map((t) => t.value)).toEqual([2, 3, 4]);
  });

  it("offers CISA 2-4 and DoD 2-3 — the ceiling is per framework", async () => {
    const { ZT_TARGET_STAGES } = await import("./types");
    expect(ZT_TARGET_STAGES.zero_trust_cisa.map((s) => s.value)).toEqual([
      2, 3, 4,
    ]);
    // DoD ZTRA ends at Stage 3. Offering a 4 is the front half of #125.
    expect(ZT_TARGET_STAGES.zero_trust_dod.map((s) => s.value)).toEqual([2, 3]);
  });

  it("never offers a level below the floor", async () => {
    const { CSF_TARGET_TIERS, ZT_TARGET_STAGES } = await import("./types");
    for (const t of CSF_TARGET_TIERS) {
      expect(t.value).toBeGreaterThanOrEqual(MIN_TARGET_TIER);
    }
    for (const stages of Object.values(ZT_TARGET_STAGES)) {
      for (const s of stages) {
        expect(s.value).toBeGreaterThanOrEqual(MIN_TARGET_STAGE);
      }
    }
  });
});

describe("the cross-language copy", () => {
  /**
   * Spelled rather than imported, so an edit to `assessment-targets.ts` goes
   * red HERE with a message naming the Python file that must change with it.
   *
   * This does not prove the two agree. Nothing available can: the web
   * container mounts `apps/web`, `packages`, `package.json`,
   * `pnpm-workspace.yaml` and the lockfile — not `apps/api` — so a test that
   * read the Python constant would pass in CI and fail on every developer's
   * machine, which is worse than no check. The same reasoning, and the same
   * remedy, as `SCHEMA_REASON_PREFIX` in `lib/describe-save-error.ts`.
   * Tracked in #422.
   */
  it("spells the floor the Python side spells too", () => {
    expect(MIN_TARGET_TIER).toBe(2);
    expect(MIN_TARGET_STAGE).toBe(2);
    // apps/api/app/assessment_targets.py carries both, and
    // apps/api/tests/unit/test_intake_target_floor.py pins them there.
  });
});

/**
 * The refusal has to reach a PERSON, which is the whole point of the API half.
 *
 * `CLAUDE.md`: the endpoint is not the surface, and a test that reads the
 * endpoint proves the write rather than the claim. The Python suite proves the
 * API sends a typed `{reason, message}`; nothing there can show that the wizard
 * renders it — `IntakeWizard.tsx` and `AssessmentsView.tsx` both go through
 * `clientFacingError`, and that helper deliberately DISCARDS some refusals.
 *
 * **Both halves, because the change moved a value across that boundary.** The
 * old envelope is withheld and the new one is rendered, and a "fix" that
 * withheld wholesale would satisfy the first assertion alone.
 *
 * The payloads are copied from a real response body observed at `1281cbd`
 * (before) and produced by `_validate_targets` (after), not invented from what
 * this helper expects.
 */
describe("the typed refusal reaches the client's screen", () => {
  const FALLBACK = "Failed to submit intake.";

  it("rendered nothing useful BEFORE: a schema_* reason is withheld", () => {
    const before = {
      status: 422,
      payload: {
        error: {
          code: 422,
          message: "Request validation failed.",
          reason: "schema_greater_than_equal",
          details: [
            {
              type: "greater_than_equal",
              loc: ["body", "service_requests", 0, "csf_target_tier"],
              msg: "Input should be greater than or equal to 2",
              input: 1,
              ctx: { ge: 2 },
            },
          ],
        },
      },
    };
    // The client was told only that it failed — not which field, nor the range.
    expect(clientFacingError(before, FALLBACK)).toBe(FALLBACK);
  });

  it("renders the typed message AFTER, in place of the fallback", () => {
    const after = {
      status: 422,
      payload: {
        error: {
          code: 422,
          message:
            "Tier 1 is where an organization starts, not a target to aim at. Choose Tier 2 or higher.",
          reason: "csf_target_tier_out_of_range",
        },
      },
    };
    const shown = clientFacingError(after, FALLBACK);
    expect(shown).not.toBe(FALLBACK);
    expect(shown).toContain("Tier 2 or higher");
  });

  it("renders the ZT stage refusal too, and names the control", () => {
    const after = {
      status: 422,
      payload: {
        error: {
          code: 422,
          message:
            "Stage 1 is where an organization starts, not a target to aim at. Choose Stage 2 or higher.",
          reason: "zt_target_stage_out_of_range",
        },
      },
    };
    expect(clientFacingError(after, FALLBACK)).toContain("Stage 2 or higher");
  });
});
