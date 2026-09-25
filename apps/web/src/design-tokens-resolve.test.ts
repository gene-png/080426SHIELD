// @vitest-environment node
/**
 * Every Tailwind colour utility that names a design-system token must COMPILE
 * to a rule (#151).
 *
 * A `className` is a string, and a utility naming a token the preset does not
 * define compiles to no CSS at all: `hover:bg-surface-muted` emitted nothing,
 * and `ring-brand-200` emitted no ring colour. Typecheck, ESLint and every
 * other test passed over them.
 *
 * The verdict is TAILWIND'S, not a reading of the preset: every candidate is
 * handed to the real compiler (`@tailwindcss/postcss` with this app's own
 * config), and a candidate is defined only if its class appears in the CSS
 * that comes back. The token namespaces are taken from the preset object, so a
 * namespace added there is covered without anyone editing this file.
 *
 * LIMITS, stated so a green run is not read as more than it is:
 *  - A candidate is a utility from COLOUR_UTILITIES below, a hand-written list,
 *    followed by a PRESET namespace. A utility missing from that list is not a
 *    candidate. So is a MISSPELLED namespace: `bg-surfce-card` names no preset
 *    namespace, is never compiled, and passes. Stock palettes, spacing,
 *    typography and arbitrary values are not checked (#608).
 *  - Runtime assembly is flagged only in three shapes: a preset namespace
 *    followed by `${` (`bg-status-${tone}-fg`, `bg-status-warning-${x}`), by a
 *    closing quote and `+` (`"bg-status-" + tone`), or preceded by `}-`
 *    (`${u}-surface-card`). Any other construction is unseen (#608).
 *  - `*.test.ts` / `*.test.tsx` files are excluded: tests quote class names as
 *    fixtures and needles, including the undefined ones this file names as
 *    negative controls, and Tailwind does not ship them to a browser.
 *  - Variants and modifiers are stripped before compiling (`hover:`, `/50`),
 *    so this proves the utility exists, not that every variant of it does.
 */
import {
  mkdtempSync,
  readFileSync,
  readdirSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import tailwind from "@tailwindcss/postcss";
import postcss from "postcss";
import { describe, expect, it } from "vitest";

// Imported at RUNTIME through a variable, not with a static `import`: a static
// import pulls `tailwind-preset.ts` into apps/web's tsc program, and that file's
// `import type ... from "tailwindcss"` does not resolve from
// `packages/design-system`, which declares no tailwindcss dependency -- CI's
// web typecheck and `next build` both failed on it (review of f765535).
// Vitest's module runner resolves and transforms it here exactly as before.
const PRESET = "@shield/design-system/tailwind-preset";
const { default: preset } = (await import(/* @vite-ignore */ PRESET)) as {
  default: { theme: { extend: { colors: Record<string, unknown> } } };
};

const WEB = resolve(fileURLToPath(new URL(".", import.meta.url)), "..");
const CONFIG = join(WEB, "tailwind.config.ts");
// The same two trees tailwind.config.ts gives as `content`.
const ROOTS = [
  join(WEB, "src"),
  resolve(WEB, "../../packages/design-system/src"),
];

const COLOUR_UTILITIES = [
  "ring-offset",
  "border-t",
  "border-b",
  "border-l",
  "border-r",
  "border-x",
  "border-y",
  "border-s",
  "border-e",
  "placeholder",
  "decoration",
  "outline",
  "divide",
  "border",
  "accent",
  "stroke",
  "shadow",
  "caret",
  "text",
  "fill",
  "ring",
  "from",
  "via",
  "bg",
  "to",
  // Tailwind v4 colour utilities (review of f765535).
  "drop-shadow",
  "inset-ring",
  "inset-shadow",
  "text-shadow",
].sort((a, b) => b.length - a.length); // longest first, so `text-shadow` wins over `text`
const NAMESPACES = Object.keys(preset.theme.extend.colors);

const alt = (xs: string[]) => xs.map((x) => x.replace(/[-]/g, "\\-")).join("|");
// A candidate: optional variants, a colour utility, a preset namespace, an
// optional key, an optional modifier. Bounded so `xbg-surface` does not match.
const CANDIDATE = new RegExp(
  `(?<![\\w-])(?:[\\w\\[\\]&.-]+:)*!?((?:${alt(COLOUR_UTILITIES)})-(?:${alt(NAMESPACES)})(?:-[\\w-]+)?)(?:/[\\w.\\[\\]]+)?(?![\\w-])`,
  "g",
);
// A class assembled at runtime from a preset namespace, in the three shapes
// LIMITS names: namespace then `${`, namespace then a closing quote and `+`,
// or `}-` then a namespace.
const DYNAMIC = new RegExp(
  [
    `(?<![\\w-])(?:${alt(COLOUR_UTILITIES)})-(?:${alt(NAMESPACES)})(?:-[\\w-]*)?\\$\\{`,
    `(?<![\\w-])(?:${alt(COLOUR_UTILITIES)})-(?:${alt(NAMESPACES)})-[\\w-]*["'\`]\\s*\\+`,
    `\\}-(?:${alt(NAMESPACES)})-`,
  ].join("|"),
  "g",
);

function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (name === "node_modules") continue;
    if (statSync(p).isDirectory()) out.push(...sourceFiles(p));
    else if (/\.(ts|tsx)$/.test(name) && !/\.test\.tsx?$/.test(name))
      out.push(p);
  }
  return out;
}

function scan(): { uses: Map<string, string[]>; dynamic: string[] } {
  const uses = new Map<string, string[]>();
  const dynamic: string[] = [];
  for (const root of ROOTS) {
    for (const file of sourceFiles(root)) {
      const text = readFileSync(file, "utf8");
      const where = relative(resolve(WEB, "../.."), file).replace(/\\/g, "/");
      for (const m of text.matchAll(CANDIDATE)) {
        const list = uses.get(m[1]) ?? [];
        list.push(where);
        uses.set(m[1], list);
      }
      for (const m of text.matchAll(DYNAMIC)) dynamic.push(`${where}: ${m[0]}`);
    }
  }
  return { uses, dynamic };
}

/** Tailwind's own answer: which of these candidates emit a rule? */
async function emitted(candidates: string[]): Promise<Set<string>> {
  const dir = mkdtempSync(join(tmpdir(), "tw-tokens-"));
  try {
    const src = join(dir, "candidates.html");
    writeFileSync(src, `<div class="${candidates.join(" ")}"></div>\n`);
    const css = [
      `@import "tailwindcss/theme.css" layer(theme);`,
      `@import "tailwindcss/utilities.css" layer(utilities) source(none);`,
      `@config "${CONFIG.replace(/\\/g, "/")}";`,
      `@source "${src.replace(/\\/g, "/")}";`,
    ].join("\n");
    const result = await postcss([tailwind({ base: dir })]).process(css, {
      from: join(dir, "in.css"),
    });
    // A class counts as emitted if its selector appears anywhere in the
    // output, not only as `.x {`: `divide-*` compiles to a child selector
    // (`.divide-x > :not(:last-child)`). Candidates carry no variant or
    // modifier, so they contain only [a-z0-9-] and need no CSS escaping.
    const out = new Set<string>();
    for (const c of candidates) {
      if (new RegExp(`\\.${c}(?![\\w-])`).test(result.css)) out.add(c);
    }
    return out;
  } finally {
    // One temp directory per call, removed whatever happened (review of f765535).
    rmSync(dir, { recursive: true, force: true });
  }
}

// One real compile is several seconds in the container, past vitest's 5s default.
const COMPILE_TIMEOUT_MS = 120_000;

describe("design-system colour tokens (#151)", () => {
  const { uses, dynamic } = scan();

  it("scans the trees Tailwind reads, and finds candidates in them", () => {
    // A scan that finds nothing is not a clean scan.
    expect(uses.size).toBeGreaterThan(20);
  });

  it(
    "the compiler emits a rule for a defined token and none for an undefined one",
    async () => {
      // Positive and negative controls, so the verdict below can fail both ways.
      const got = await emitted([
        "bg-surface-card",
        "border-border",
        "divide-border-subtle",
        "bg-surface-muted",
      ]);
      expect(got.has("bg-surface-card")).toBe(true);
      expect(got.has("border-border")).toBe(true);
      // A child-selector utility: the emission check must not require `.x {`.
      expect(got.has("divide-border-subtle")).toBe(true);
      expect(got.has("bg-surface-muted")).toBe(false);
    },
    COMPILE_TIMEOUT_MS,
  );

  it("no class is assembled at runtime from a preset namespace (could not look)", () => {
    // The detector itself, so an empty list is not a detector that matches nothing.
    // Each of the three shapes LIMITS names is recognised.
    const D = "$";
    for (const shape of [
      `bg-status-${D}{tone}-fg`,
      `bg-status-warning-${D}{x}`,
      `"bg-status-" + tone`,
      `${D}{u}-surface-card`,
    ]) {
      expect([...shape.matchAll(DYNAMIC)], shape).toHaveLength(1);
    }
    expect(dynamic).toEqual([]);
  });

  it(
    "every preset colour utility in the source compiles to a rule",
    async () => {
      const candidates = [...uses.keys()].sort();
      const got = await emitted(candidates);
      const undefinedTokens = candidates
        .filter((c) => !got.has(c))
        .map((c) => `${c}  (${[...new Set(uses.get(c))].join(", ")})`);
      expect(undefinedTokens).toEqual([]);
    },
    COMPILE_TIMEOUT_MS,
  );
});
