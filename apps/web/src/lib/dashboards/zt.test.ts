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
