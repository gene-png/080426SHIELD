import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * #554, #621 review. The owner's rule: no surface showing an ATT&CK coverage
 * figure may drop the not-verified count. The first version of this check was
 * a hand-kept list of surfaces, and it missed three (the client KPI row and
 * triad, the home value card, the admin matrix header).
 *
 * So the set is DERIVED here, not listed. A component is in scope when it
 * reads ATT&CK data (imports from `@/lib/attack/` or `@/lib/dashboards/attack`)
 * and, outside comments, renders a coverage figure:
 *   * a percentage -- `coverage_pct`, `dprCoverage(` or `kpis(` -- must call
 *     `outsideAssessedText`;
 *   * the uncovered count -- `attack_uncovered_count` -- must render
 *     `attack_not_verified_count` beside it.
 * A new surface matching either shape turns this red until it states the
 * counts, which is the point.
 *
 * What it walks: every `.tsx` under `src`, components AND pages, tests
 * excluded. What this cannot see: a figure computed in a `.ts` file (it is
 * rendered in a `.tsx` that the scan does reach), a figure computed under
 * another name, a file that
 * receives ATT&CK data only through props typed elsewhere, and a SECOND figure
 * in a file that already states the counts once -- it asks whether a file
 * mentions them at all. That each figure has them beside it is each surface's
 * own test (AttackDashboard.statuses, AttackMatrix, AttackHeatmapCard,
 * ValueLoopCard). It is a floor, and it exists for the surface nobody has
 * written a test for yet.
 */

// ALL of `src`: pages under `src/app/**` are surfaces too (#621 round 2).
const ROOT = join(process.cwd(), "src");

function walk(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...walk(full));
    else if (/\.tsx$/.test(entry) && !/\.(test|spec)\.tsx$/.test(entry))
      out.push(full);
  }
  return out;
}

/** Source with comment lines dropped, so a docstring naming `coverage_pct`
 *  does not make a file a surface. */
function code(body: string): string {
  return body
    .split("\n")
    .filter((line) => !/^\s*(\/\/|\*|\/\*|\{\/\*)/.test(line))
    .join("\n");
}

const READS_ATTACK = /from "@\/lib\/(attack\/|dashboards\/attack")/;
const PERCENT = /coverage_pct|dprCoverage\(|\bkpis\(/;
const UNCOVERED = /attack_uncovered_count/;

const FILES = walk(ROOT).map((f) => ({
  path: relative(process.cwd(), f).replace(/\\/g, "/"),
  body: readFileSync(f, "utf8"),
}));

const PERCENT_SURFACES = FILES.filter(
  (f) => READS_ATTACK.test(f.body) && PERCENT.test(code(f.body)),
);
const UNCOVERED_SURFACES = FILES.filter((f) => UNCOVERED.test(code(f.body)));

describe("every ATT&CK coverage figure states the outside counts (#554)", () => {
  it("found the surfaces it is known to have, so an empty scan cannot pass", () => {
    // Asserted FIRST: a walker pointed at the wrong directory selects nothing
    // and the two checks below would pass over nothing.
    const paths = PERCENT_SURFACES.map((f) => f.path);
    expect(paths).toEqual(
      expect.arrayContaining([
        "src/components/admin/attack/AttackHeatmapCard.tsx",
        "src/components/admin/attack/AttackMatrix.tsx",
        "src/components/dashboards/attack/AttackDashboard.tsx",
      ]),
    );
    expect(UNCOVERED_SURFACES.map((f) => f.path)).toContain(
      "src/components/home/ValueLoopCard.tsx",
    );
  });

  it.each(PERCENT_SURFACES.map((f) => [f.path, f.body] as const))(
    "%s renders a percentage and calls outsideAssessedText",
    (_path, body) => {
      expect(code(body)).toMatch(/outsideAssessedText\(/);
    },
  );

  it.each(UNCOVERED_SURFACES.map((f) => [f.path, f.body] as const))(
    "%s renders the uncovered count and the not-verified count beside it",
    (_path, body) => {
      expect(code(body)).toMatch(/attack_not_verified_count/);
    },
  );
});
