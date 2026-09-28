import { describe, expect, it } from "vitest";

import {
  pillarsByGap,
  radarData,
  targetNote,
  type ZtDashboardData,
  type ZtPillar,
} from "./zt";

function pillar(p: Partial<ZtPillar>): ZtPillar {
  return {
    code: "ID",
    name: "Identity",
    capability_count: 5,
    answered_count: 5,
    current_pct: 50,
    current_label: "Initial",
    target_pct: 100,
    target_label: "Optimal",
    gap_pct: 50,
    weakest: [],
    ...p,
  };
}

const PILLARS: ZtPillar[] = [
  pillar({ name: "Identity", current_pct: 75, target_pct: 95, gap_pct: 20 }),
  pillar({ name: "Data", current_pct: 50, target_pct: 90, gap_pct: 40 }),
  pillar({ name: "Networks", current_pct: 68, target_pct: 90, gap_pct: 22 }),
];

describe("zt dashboard transforms", () => {
  it("radarData: current + target series in pillar order", () => {
    const r = radarData(PILLARS);
    expect(r.labels).toEqual(["Identity", "Data", "Networks"]);
    expect(r.current).toEqual([75, 50, 68]);
    expect(r.target).toEqual([95, 90, 90]);
  });

  it("radarData: null pct coerces to 0", () => {
    const r = radarData([pillar({ current_pct: null, target_pct: null })]);
    expect(r.current).toEqual([0]);
    expect(r.target).toEqual([0]);
  });

  it("pillarsByGap: largest gap first", () => {
    expect(pillarsByGap(PILLARS).map((p) => p.name)).toEqual([
      "Data",
      "Networks",
      "Identity",
    ]);
  });
});

function data(p: Partial<ZtDashboardData>): ZtDashboardData {
  return {
    service_id: "s",
    unusable_target_codes: [],
    service_title: "Atlas — Zero Trust",
    released_at: "2026-09-06T00:00:00Z",
    deliverable_version: 1,
    framework: "cisa_ztmm_2_0",
    framework_label: "CISA ZTMM 2.0",
    current_label: "Initial",
    current_pct: 50,
    target_label: "Optimal",
    target_pct: 100,
    target_stage: 4,
    target_stage_source: "client",
    // #209. Defaulting to FROZEN, because that is what every deliverable this
    // product builds carries. A base fixture defaulting to the legacy null
    // would make every unrelated case here exercise a disclosure path only
    // pre-0051 rows can reach; the tests for that path override it.
    target_frozen_at: "2026-09-06T00:00:00Z",
    engagement_target_capability_count: 37,
    total_gap_count: 37,
    largest_gap_pillar: "Identity",
    largest_gap_pct: 50,
    pillars: PILLARS,
    ...p,
  };
}

describe("zt target provenance", () => {
  // #124: the client read "Target maturity: Unscored · +0 points to target"
  // beside a released PDF listing 37 gaps at Stage 4. A target nobody chose
  // must never render like one they did — and the reverse must also hold.
  it("targetNote: each source gets its own sentence", () => {
    const note = (src: string): string =>
      targetNote(data({ target_stage_source: src }));

    expect(note("client")).toBe("Your target, chosen at intake");
    expect(note("default")).toBe("Default target — no stage chosen at intake");
    // The two failure sources must NOT collapse into the "chose nothing"
    // wording: the client did choose, and a consultant can re-ask them.
    expect(note("client_out_of_range")).toBe(
      "Default target — the stage on file is not one this framework has",
    );
    expect(note("client_unparseable")).toBe(
      "Default target — the stage on file could not be read",
    );

    const notes = [
      "client",
      "default",
      "client_out_of_range",
      "client_unparseable",
    ].map(note);
    expect(new Set(notes).size, "each source must be distinguishable").toBe(4);
  });

  it("targetNote: an unknown source never claims the client chose it", () => {
    // Fails safe toward "assumed". #124's whole failure mode was a fallback
    // that read like a decision.
    expect(targetNote(data({ target_stage_source: "something_new" }))).toBe(
      "Default target — the stage on file was not usable",
    );
  });

  it("targetNote: a fully overridden target is not credited to intake", () => {
    // The engagement stage decided nothing, so naming it as the source would
    // caption the percentage with something that contributed none of it.
    expect(
      targetNote(
        data({
          target_stage_source: "client",
          engagement_target_capability_count: 0,
        }),
      ),
    ).toBe("Per-capability targets from your assessment");
  });

  it("targetNote: a fully overridden target still reports a FAILED choice", () => {
    // The state that is easiest to lose: every per-row target set AND the
    // stored stage unusable. An early return here would swallow the one thing
    // a consultant can act on -- in the function written to keep these apart.
    // Reachable exactly as `test_dashboard_reports_an_out_of_range_stored_
    // target_rather_than_500ing` builds it, plus a Run-AI pass.
    for (const src of ["client_out_of_range", "client_unparseable"]) {
      const note = targetNote(
        data({
          target_stage_source: src,
          engagement_target_capability_count: 0,
        }),
      );
      expect(note, `${src} must not be swallowed`).toContain(
        "Per-capability targets from your assessment",
      );
      expect(note, `${src} must still name the fault`).toContain(
        "the stage on file",
      );
    }
  });

  it("targetNote: a fully overridden target does NOT nag about an absent choice", () => {
    // "default" is not a fault -- the client chose nothing, which is not
    // actionable, and when the engagement stage decided no capability either
    // the absence never reached the page. Appending it would be noise about a
    // value nobody used.
    expect(
      targetNote(
        data({
          target_stage_source: "default",
          engagement_target_capability_count: 0,
        }),
      ),
    ).toBe("Per-capability targets from your assessment");
  });

  it("targetNote: one capability on the engagement target still credits it", () => {
    // The boundary the check above turns on. At 1 the intake choice decides a
    // real capability, so the client-chosen wording is the honest one.
    expect(
      targetNote(
        data({
          target_stage_source: "client",
          engagement_target_capability_count: 1,
        }),
      ),
    ).toBe("Your target, chosen at intake");
  });
});

describe("targetNote — a discarded per-capability target reaches the screen (#387)", () => {
  /**
   * `unusable_target_codes` has been served since #188 and rendered by nothing,
   * while the client's PDF said it in `_gap_plan_caption`. A fact in the
   * deliverable and absent from the screen is two surfaces reading one
   * assessment and disagreeing.
   */
  it("names the rows whose per-capability target could not be used", () => {
    const note = targetNote(
      data({
        target_stage_source: "client",
        engagement_target_capability_count: 3,
        unusable_target_codes: ["CISA.ID.01", "CISA.DE.02"],
      }),
    );
    // THE WHOLE STRING, not `toContain`. Containment left three natural
    // mutants alive, and the adversarial review found all three: a different
    // `join` separator, the two sentences concatenated in REVERSE order
    // (`discarded.concat(base)` -- which every exact-`toBe` provenance test
    // above still passes, because the empty case is `"".concat(base) ===
    // base`), and a doubled append. One equality kills all three, and it is
    // also the only assertion that can see a stray space or a missing one.
    expect(note).toBe(
      "Your target, chosen at intake A per-capability target was recorded for" +
        " CISA.ID.01, CISA.DE.02 but could not be used, so the engagement" +
        " target was applied to those rows instead.",
    );
  });

  it("says nothing when every per-capability target was usable", () => {
    // The other half. A fix that appends unconditionally passes the test above
    // and puts a fault sentence on every ordinary engagement.
    const note = targetNote(
      data({
        target_stage_source: "client",
        engagement_target_capability_count: 3,
        unusable_target_codes: [],
      }),
    );
    expect(note).not.toContain("could not be used");
    expect(note).toContain("Your target, chosen at intake");
  });

  it("appends it in the fully-overridden branch too, rather than returning early", () => {
    // `engagement_target_capability_count === 0` returns early for the SUBJECT
    // of the sentence. An earlier draft of this function swallowed
    // `client_out_of_range` exactly that way; the disclosure must not go the
    // same route.
    const note = targetNote(
      data({
        target_stage_source: "default",
        engagement_target_capability_count: 0,
        unusable_target_codes: ["CISA.ID.01"],
      }),
    );
    expect(note).toBe(
      // One code, so ONE row (#452): this expected string said "those rows"
      // and pinned the grammar defect the issue is about.
      "Per-capability targets from your assessment A per-capability target was" +
        " recorded for CISA.ID.01 but could not be used, so the engagement" +
        " target was applied to that row instead.",
    );
  });

  it("says it exactly as the client's PDF says it, for ONE row (#452)", () => {
    // The singular twin of the parity pin below, TRANSCRIBED FROM THE PYTHON
    // (`_gap_plan_caption`, one code) for the same reason: two independent
    // origins, so a one-sided change goes red here.
    const fromTheDeliverable =
      " A per-capability target was recorded for CISA.ID.01 but could not be" +
      " used, so the engagement target was applied to that row instead.";
    const note = targetNote(
      data({
        target_stage_source: "client",
        engagement_target_capability_count: 3,
        unusable_target_codes: ["CISA.ID.01"],
      }),
    );
    expect(note.endsWith(fromTheDeliverable)).toBe(true);
  });

  it("says it exactly as the client's PDF says it", () => {
    // THE CROSS-SURFACE PARITY PIN, and it is the point of the whole change.
    //
    // `zt/exporters.py::_gap_plan_caption` builds this sentence for the Gap
    // Plan caption. Until this assertion existed, nothing anywhere failed if
    // the two drifted -- which is precisely the defect #387 was filed about,
    // one surface saying something the other does not.
    //
    // The expected value is TRANSCRIBED FROM THE PYTHON, not derived from
    // `targetNote`, so the two sides of this equality have independent
    // origins. `_gap_plan_caption` carries the pointer back to this test, on
    // the ORIGIN side, because whoever rewords the caption never opens a
    // TypeScript file.
    const fromTheDeliverable =
      " A per-capability target was recorded for CISA.ID.01, CISA.DE.02 but" +
      " could not be used, so the engagement target was applied to those rows" +
      " instead.";
    const note = targetNote(
      data({
        target_stage_source: "client",
        engagement_target_capability_count: 3,
        unusable_target_codes: ["CISA.ID.01", "CISA.DE.02"],
      }),
    );
    expect(note.endsWith(fromTheDeliverable)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// #209: which target the figures were computed against.
//
// BOTH BRANCHES OF `targetNote`, deliberately. It returns early-ish through two
// separate paths -- the fully-overridden one and the ordinary one -- and this
// function has twice shipped a fault that one path swallowed. A single case
// here would pass under an implementation that appends the sentence to one
// branch only, which is the defect, not a variant of it.
// ---------------------------------------------------------------------------

describe("targetNote discloses a live-read target (#209)", () => {
  const LIVE =
    " These figures use your target as it stands today. Your released report" +
    " was rendered against the target on file at the time, so the two can" +
    " differ.";

  it("appends it on the ordinary branch", () => {
    expect(targetNote(data({ target_frozen_at: null }))).toContain(LIVE);
  });

  it("appends it on the fully-overridden branch too", () => {
    expect(
      targetNote(
        data({
          target_frozen_at: null,
          engagement_target_capability_count: 0,
        }),
      ),
    ).toContain(LIVE);
  });

  it("appends it BESIDE a target fault rather than in place of one", () => {
    // The shape this function has been repaired for twice: a second fact is
    // added and an existing one stops rendering.
    const note = targetNote(
      data({
        target_frozen_at: null,
        target_stage_source: "client_out_of_range",
      }),
    );
    expect(note).toContain(LIVE);
    expect(note).toContain("Default target");
  });

  it("appends it BESIDE the discarded-capability sentence", () => {
    const note = targetNote(
      data({ target_frozen_at: null, unusable_target_codes: ["ZT-1"] }),
    );
    expect(note).toContain(LIVE);
    expect(note).toContain("A per-capability target was recorded for ZT-1");
  });

  it("says nothing extra on a frozen dashboard, on either branch", () => {
    expect(targetNote(data({}))).not.toContain("as it stands today");
    expect(
      targetNote(data({ engagement_target_capability_count: 0 })),
    ).not.toContain("as it stands today");
  });
});
