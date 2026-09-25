# 2026-09-25: a Tailwind class naming an undefined design token fails a test (#151)

Branch `track1/tailwind-token-gate`, branch-start base `2028f38`.

## Why

A utility naming a colour token the design-system preset does not define
compiles to no CSS at all, and typecheck, ESLint and every test passed over
it. On `main`, 18 occurrences across 9 files rendered nothing: hover
backgrounds, a panel background, border colours, and a focus ring.

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

These now render where they rendered nothing, so client-facing screens change
(merge-rule condition 6).

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
