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

## Round 1 (review of `9fc8eeb`)

**What the stripper cannot parse is now could-not-look.** An unclosed block
comment, a template literal open at EOF, a declaration body that never closes,
or a string in a type body that never closes each used to fall through to a
verdict, with EOF taken as the end. In the red direction, `type Brace = "{";`
above a render opened a body that never closed, and the strip ate the render.
That red is worse than it looks, because it CAN be cleared, the wrong way. The
gate's remedy for a red is an `EXEMPT_FIELDS` entry, and
`expired_field_exemptions` reads the file through the same stripper. So an
exemption written for a field that is really rendered would never be seen to
expire. (An earlier version of this entry said the red "could never be
cleared", which was backwards; corrected on review of `63430ff`.) In the green
direction, a regex literal like `/["']/` opened a phantom string, and a
comment after it cleared the field.

Now:
- both scanners raise `TsParseError`, and `reader_text` pre-parses every
  TypeScript reader, so `main` exits 2 naming the file and the cause;
- strings are skipped inside type bodies;
- regex literals are recognised by the character before the `/`.

A `'`/`"` string cannot cross a newline in TypeScript, so a quote still open at
a newline was never a string (JSX text like `Don't`). It resets there instead
of swallowing the file.

**Arm 2's twin.** `audit_payload_has_a_generic_reader` matched the raw
`AuditViewer.tsx`, so a commented-out `cell:` satisfied it. It now reads
`ts_use_text`.

**Keep-tests.** A destructured prop and a `${d.field}` template use must
survive the strip.

The real tree still reads 31 of 31, with no file exiting 2.

**Red-on-revert, 8 of 8:**
- an unclosed block comment running to EOF;
- an unclosed template accepted;
- a body ending at EOF;
- a string in a type body ending at EOF;
- strings not masked in type bodies;
- regex literals not recognised;
- the newline reset removed;
- the audit arm reading the raw file.

The EOF-string mutation was GREEN on the first run. Its only case had a
newline, so a different check fired first. A case with the quote open at the
very end of the file was added, and it is red now.

## Limits

The full list is in `ts_use_text`'s docstring, and the open ones are #632.
- A green means the field is USED outside a type declaration, in a file that
  names the model. It does not mean RENDERED: a use that feeds nothing visible
  still clears it.
- These still count as a use: an inline object-type annotation, an
  indexed-access type or `Pick<Data, "field">`, an `interface` whose generic
  holds a `{`, and a `type` alias whose generic has a default (`<T = Y>`).
- **The lexer-state class.** Whenever the lexer believes it is inside a string
  or a regex that it is not really in, it misses a comment opener for the rest
  of that line. For a block comment, every LATER line of the comment is then
  lexed as code. Three known forms, all erring green, none live:
  - JSX text with an apostrophe, `Don't {/* see` with the field on the next
    line. Backticks in that comment's prose can also flip template parity, or
    cause exit 2.
  - `}` as a regex preceder, as in `<X a={b} /> {/* field */}`.
  - A keyword before a regex (`return /'/`, `typeof /x'/`), read as division.

  An earlier version listed only "a `//` comment after a JSX apostrophe on the
  same line", which is one form of the class, not the class (review of
  `63430ff`).
- Python exporters are matched as before, comments and docstrings included.

## Round 2 (review of `63430ff`)

These changes are prose, plus one relabelled test:
- the lexer-state class is stated in the docstring and here, and #632's body
  is widened to it;
- the `TsParseError` docstring states the real hazard of the red direction;
- the module docstring's list of exit-2 branches gains the could-not-parse
  branch.

The apostrophe test is relabelled as a keep-test, and its comment now says
what it pins. It goes red if a quote open at a newline were made a
`TsParseError`; that was checked by mutation, and it was red. It does not pin
the newline reset: with the reset removed it stays green, as the review found.
The reset is pinned by the comment test beside it.
