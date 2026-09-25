# 2026-09-25: the disclosure gate counts a use, not a type declaration (#473)

Branch `track1/disclosure-use-not-declaration`, cut from `b4e6c41` and rebased
onto `aca9e79` before opening.

## Why

`check_disclosure_consumers.py` cleared a disclosure field when one file held
both the field's name and the model's subject. Every `lib/dashboards/*.ts`
declares its response shape as a TypeScript interface, so every field was
pre-cleared by its own type, with nothing rendering it.

Measured on #209's branch, 2026-09-23: deleting both renders of
`target_frozen_at` left the gate at 29 of 29, exit 0. That is #322's defect
shape: data that reaches the browser and is discarded there.

## What changed

For a TypeScript reader, `readers_for` now matches the FIELD against
`ts_use_text`, which removes three things:
- `//` and `/* */` comments, string-aware, so `//` inside a URL is kept;
- `interface` bodies, brace-balanced;
- `type` alias bodies, up to their depth-0 `;`.

The SUBJECT is still matched against the whole file, because the type name is
usually where a file names its model.

Balancing counts `{}`, `()` and `[]`, and deliberately not `<>`: the `>` of an
arrow type (`() => void`) would unbalance it. A first draft did count them.

#473's preferred option was to exclude the response-type modules from the
readers. It was not taken, because `lib/dashboards/zt.ts` both declares the
interface and builds the rendered note, so excluding the file would drop a
real use.

## Measured

- On the real tree, before and after the rebase (`b4e6c41` and `aca9e79`),
  the new gate reads 31 of 31, exit 0. Every disclosure field has a use outside
  comments and type declarations, so no false red.
- **#473's own mutation**, run on the real tree: `zt.ts` with
  `renderedAgainstNote(null)`, and the `.concat(...)` deleted from
  `CsfDashboard.tsx`. The new gate exits 1 and names both
  `CsfDashboardResponse.target_frozen_at` and
  `ZtDashboardResponse.target_frozen_at` -- re-run after the rebase, same
  result. `main`'s gate over the same deletion
  reads 31 of 31, exit 0. Both files were restored.

## Verified

- New tests in `test_disclosure_consumers.py`:
  - a field only declared in an interface (placed after an arrow type and a
    nested object) is a violation;
  - declared and used in the same file passes;
  - a `type` alias (same line, and body on the next line), a line comment and
    a block comment are each a violation;
  - `//` inside a string does not hide a use;
  - a subject named only in the interface still attributes a real use.
- Red-on-revert, 6 of 6:
  - declarations counted as uses;
  - both `<>` counted;
  - an interface ending at its first `}`;
  - comments not stripped;
  - the stripper not string-aware;
  - a type alias ending at a newline.

  One earlier mutation, adding `<` alone, was GREEN. `=>` has no `<`, so it
  never exercised the defect, and it is not counted above.

## Limits

- A green means the field is USED outside a type declaration, in a file that
  names the model. It does not mean RENDERED: a use that feeds nothing visible
  still clears it.
- A field name inside a string literal counts as a use, so
  `Pick<Data, "field">` would clear it.
- An inline object type in a parameter annotation is not stripped.
- Python exporters are matched as before.
