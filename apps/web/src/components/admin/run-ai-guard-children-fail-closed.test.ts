import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Every Run-AI control disables itself while the AI status cannot be read
 * (#645). `RunAiGuard` hands its child `statusUnknown`; a control that ignores
 * it stays clickable, and a click is then refused by the guard with a notice,
 * which is better than running but is not "disabled while unknown".
 *
 * Derived from the source tree, so a new Run-AI surface is covered the day it
 * renders a `<RunAiGuard>`. Tests and the guard itself are excluded.
 */
const SRC = join(process.cwd(), "src");

function sources(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const p = join(dir, entry);
    if (statSync(p).isDirectory()) out.push(...sources(p));
    else if (/\.tsx$/.test(entry) && !/\.test\.tsx$/.test(entry)) out.push(p);
  }
  return out;
}

describe("Run-AI controls fail closed on an unreadable AI status (#645)", () => {
  const surfaces = sources(SRC).filter((p) => {
    const text = readFileSync(p, "utf8");
    return text.includes("<RunAiGuard") && !p.endsWith("RunAiGuard.tsx");
  });

  it("finds the Run-AI surfaces at all", () => {
    // ATT&CK, CSF, ZT, the Tech Debt documents panel, and Risk.
    expect(surfaces.length).toBeGreaterThanOrEqual(5);
  });

  it("disables every guarded control while the status is unknown", () => {
    const ignoring = surfaces
      .filter((p) => {
        const text = readFileSync(p, "utf8");
        return !(
          text.includes("{({ onClick, statusUnknown }) =>") &&
          /disabled=\{[^}]*statusUnknown/s.test(text)
        );
      })
      .map((p) => relative(SRC, p));
    expect(
      ignoring,
      "these Run-AI controls stay enabled while the AI status is unknown",
    ).toEqual([]);
  });
});
