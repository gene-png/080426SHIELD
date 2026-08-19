import { describe, expect, it } from "vitest";

import { dashboardPathFor } from "./routes";

/**
 * This map is the single source of truth for client dashboard links, and it had
 * no test. A missing case here is not a crash — it is a `null`, which callers
 * turn into a missing link, so the failure mode is a service the client simply
 * cannot open. That is exactly how `nist_csf` stayed unreachable.
 */
describe("dashboardPathFor", () => {
  it.each([
    ["attack_coverage", "/dashboards/attack/s1"],
    ["zero_trust_cisa", "/dashboards/zt/s1"],
    ["zero_trust_dod", "/dashboards/zt/s1"],
    ["tech_debt", "/dashboards/tech-debt/s1"],
    ["nist_csf", "/dashboards/csf/s1"],
  ])("maps %s to its dashboard", (kind, expected) => {
    expect(dashboardPathFor(kind, "s1")).toBe(expected);
  });

  it("returns null only for kinds that genuinely have no dashboard", () => {
    // `consultation` is advisory work with no assessment behind it, so there is
    // nothing to render. Callers must fall back rather than emit a dead link.
    expect(dashboardPathFor("consultation", "s1")).toBeNull();
  });

  it("returns null for an unknown kind rather than inventing a path", () => {
    // A service kind this build does not know about must not produce a URL that
    // 404s — the caller decides what to show instead.
    expect(dashboardPathFor("something_new", "s1")).toBeNull();
  });

  it("every assessment service is reachable", () => {
    // The regression that mattered: CSF was the only assessment service
    // returning null, so a client saw its gap count on /home and could not open
    // the results. If a new assessment service is added, it belongs here.
    const assessmentKinds = [
      "attack_coverage",
      "zero_trust_cisa",
      "zero_trust_dod",
      "tech_debt",
      "nist_csf",
    ];
    for (const kind of assessmentKinds) {
      expect(dashboardPathFor(kind, "s1")).not.toBeNull();
    }
  });
});
