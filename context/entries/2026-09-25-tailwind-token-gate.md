# 2026-09-25: a Tailwind colour class naming a preset namespace but an undefined token fails a test (#151)

Branch `track1/tailwind-token-gate`, branch-start base `2028f38`.

## Why

A utility naming a colour token the design-system preset does not define
compiles to no CSS at all, and typecheck, ESLint and every test passed over
it. On `main` there were 18 such occurrences across 9 files. What each looked
like before the fix, per class:

- `bg-surface-muted` (3): no background. Two are panels (the MFA "Setup key"
  box and the AI-preview result panel), which were transparent over their
  parent; the third is WorkflowStep's BLOCKED-step number badge, which showed
  a bare number and now shows a grey disc.
- `bg-surface-default` (1): the AI-preview `<pre>` code block had no
  background and is now white (surface-card).
- `hover:bg-surface-muted` (6): no hover background on six secondary buttons.
- `border-border-default` (7): no utility, BUT `globals.css`'s `*` rule
  already sets `border-color: var(--border-default)`, so these borders looked
  as intended, and still do.
- `ring-brand-200` (1): the ring itself existed (`ring-2`), in its default
  colour; the ProgressStages current-stage halo is RECOLOURED to brand-300,
  not made to appear.

## What changed

- **`apps/web/src/design-tokens-resolve.test.ts`** (vitest, so it runs in
  CI's web job). It collects every colour utility (`bg-`, `text-`, `border-`,
  `ring-`, ...) that names a PRESET namespace (`surface`, `ink`, `border`,
  `brand`, `status`, taken from the preset object) from string literals in
  the two trees `tailwind.config.ts` scans. It then asks TAILWIND, not a
  reading of the preset: every candidate goes through `@tailwindcss/postcss`
  with this app's own config, and a class counts as defined only if its
  selector appears in the CSS that comes back. Positive and negative controls
  (including a child-selector utility, `divide-border-subtle`) make the
  verdict able to fail both ways. A class assembled at runtime from a preset
  namespace fails as "could not look", and the detector for it is itself
  tested.
- **The 18 occurrences are fixed**, each to the repo's existing idiom for the
  intent (my call, overturnable):
  - `bg-surface-muted` and `hover:bg-surface-muted` → `...-surface-sunken`
    (the hover background is `hover:bg-surface-sunken` in 39 other places);
  - `border-border-default` → `border-border` (the preset's `DEFAULT` maps to
    the bare namespace class, used 110 times);
  - `bg-surface-default` → `bg-surface-card`;
  - `ring-brand-200` → `ring-brand-300`, the nearest defined step.

So what changes on screen: four backgrounds and six hover states appear, and
one halo is recoloured; the seven border sites look the same. That is
client-facing (merge-rule condition 6).

## Proof

Before the class fixes, the test failed listing exactly the four undefined
tokens and their files. After them, vitest passes on the worktree: 74 files,
869 tests (`scripts/verify-in-worktree.sh vitest`). Red on revert, three
mutations, each red on its named test: a fixed class reverted; the emission
check narrowed to `.x {` (the child-selector control goes red); every
candidate reported as emitted (the negative control goes red).

## Limits

Only colour utilities naming a preset namespace are checked. Stock palettes,
spacing, typography and arbitrary values are not. Variants and modifiers are
stripped before compiling, so it proves the utility exists, not every variant
of it.

## After the first review (`f765535`)

- **CI was red, and I had dismissed the signal.** The static import of the
  preset pulled `tailwind-preset.ts` into apps/web's tsc program, and its
  `import type ... from "tailwindcss"` does not resolve from
  `packages/design-system`, which declares no tailwindcss dependency. CI's
  typecheck and `next build` both failed. My local run showed the same error
  and I set it aside as the #175 mount artifact without checking. The preset
  is now imported at runtime through a variable, which vitest resolves and
  tsc does not follow. Proved in a CLEAN container (`node:22-bookworm`, a
  copy of the tree, `pnpm install --frozen-lockfile`): typecheck exit 0,
  `pnpm -F web build` exit 0 with CI's env, the test 4 passed. With the static
  import put back, the same clean typecheck exits 2 with CI's exact TS2307.
- **LIMITS narrowed to what is caught**, by the coordinator's call: the
  hand-written utility list (now with v4's `drop-shadow-`, `inset-ring-`,
  `inset-shadow-`, `text-shadow-`), a misspelled namespace passing, the
  three runtime-assembly shapes flagged and no others, and why `*.test.ts(x)`
  is excluded. The residuals are filed as #608.
- **Runtime assembly** is flagged in three shapes now (namespace then `${`,
  namespace then a quote and `+`, `}-` then a namespace), each tested.
- **The temp directory** is removed in a `finally`.
- **The rendering description** is per class (above): the border sites look
  unchanged, and the ring is a recolour.

