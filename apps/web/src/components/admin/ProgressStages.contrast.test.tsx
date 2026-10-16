// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ProgressStages, type Stage } from "./ProgressStages";

/**
 * #1356: every stage label must read at WCAG AA (4.5:1) on the sunken surface,
 * the darkest surface the bar renders on (admin layout; IntakeQueue's is a white
 * card, which is lighter). The pending label was `text-slate-400` (#90a1b9 on #eef2f7,
 * 2.33:1), which s16's axe scan caught whenever the bar had rendered.
 *
 * Colours are resolved from the design tokens file, not copied, so a token
 * change is judged by its real value. Tailwind's own palette is not in that
 * file, so its classes are pinned to their Tailwind values here (tailwindcss
 * 4.3.3, apps/web/package.json; re-check them on a Tailwind bump): slate-700
 * (complete), and slate-400, the pending colour #1356 replaced, kept so that
 * reverting the fix fails on its measured ratio (2.33) rather than on a lookup.
 */
const TOKENS = readFileSync(
  join(process.cwd(), "../../packages/design-system/src/tokens.css"),
  "utf8",
);
const TAILWIND: Record<string, string> = {
  "slate-400": "#90a1b9",
  "slate-700": "#314158",
};

function token(name: string): string {
  const m = new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`).exec(TOKENS);
  if (!m) throw new Error(`no hex value for --${name} in tokens.css`);
  return m[1];
}

/** The text colour a `text-*` class resolves to. */
function colourOf(cls: string): string {
  const name = cls.replace(/^text-/, "");
  if (TAILWIND[name]) return TAILWIND[name];
  return token(name);
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const STAGES: Stage[] = [
  { key: "prepare", state: "complete" },
  { key: "analyze", state: "current" },
  { key: "review", state: "pending" },
  { key: "approve", state: "pending" },
  { key: "generate", state: "pending" },
  { key: "release", state: "pending" },
];

/** The colour class on a stage's visible label. */
function labelColour(text: string): string {
  const el = screen.getByText(text, { selector: "span:not(.sr-only)" });
  const cls = el.className.split(/\s+/).find((c) => /^text-(?!sm\b)/.test(c));
  if (!cls) throw new Error(`no text colour class on "${text}"`);
  return cls;
}

describe("ProgressStages label contrast (#1356)", () => {
  const sunken = token("surface-sunken");

  it.each([
    ["Prepare", "complete"],
    ["Analyze", "current"],
    ["Review", "pending"],
    ["Release", "pending"],
  ])("%s (%s) reads at 4.5:1 or better on the sunken surface", (text) => {
    render(<ProgressStages stages={STAGES} kind="tech_debt" />);
    const ratio = contrast(colourOf(labelColour(text)), sunken);
    expect(ratio).toBeGreaterThanOrEqual(4.5);
  });

  it("keeps pending visibly lighter than complete", () => {
    render(<ProgressStages stages={STAGES} kind="tech_debt" />);
    const pending = contrast(colourOf(labelColour("Review")), sunken);
    const complete = contrast(colourOf(labelColour("Prepare")), sunken);
    expect(pending).toBeLessThan(complete);
  });
});
