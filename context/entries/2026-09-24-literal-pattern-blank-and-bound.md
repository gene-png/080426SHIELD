# 2026-09-24: a blank redaction literal is a typed error, and the name matcher's cost is in the code

Branch `fix/literal-pattern-typed-empty`, base `d11613e` (#542). These are
follow-ups the owner raised in their review of #542.

## A blank needle raises, typed

`_literal_pattern` and `_literal_edges` raised a bare `IndexError` at
`tokens[0]` when the needle was `""`, `" "` or a no-break space. That was not
reachable, because `redact_org_name` guards with `.strip()` and `_redact_names`
drops short hints after normalising. But the only protection was a docstring
sentence ("Callers must pass a needle with at least one non-space
character"), and `IndexError` is not a typed error under D-016.

Both functions now split through `_needle_tokens`, which raises
`BlankRedactionLiteralError`: an `HTTPException` with the detail
`{reason: "redaction_blank_literal", message}`, the same shape as
`MissingFixtureError`. It raises and never skips, because this is the egress
path and a skipped needle would redact less and say nothing.

Red-on-revert: deleting the raise turned every blank-needle case red.

## The cost, bounded and written at the loop

The owner asked for one adversarial measurement before the performance
question closed. The comment above the loop in `_redact_names` now states the
bound, which factors were measured, and where the runs are.

- **The bound is O(H × L × T).** T is the text length, L the longest hint in
  characters, and H the number of hints in one anchor group, which is compiled
  as a single alternation.
- **H and T were measured; L was argued from the code.** Every series used
  hints of about 250 characters, so L was never varied.
- **The measured worst case is 427–556 ns per hint per character**, for H = 1
  to 1024, in the api image. H = 64 is about 32 s per MB.
- **Prefix hoisting only helps within the first word.** CPython hoists a
  prefix shared by every alternative, but only up to the first `\s+`.
- **L is bounded at 255 by the schema.** Hints come from `display_name`, and
  from email local parts, which `EmailStr` keeps under 254. H is bounded by
  nothing, and is filed as #546.
- **A stall does not stop egress.** The request runs on after the caller gives
  up, and it calls the provider.

**Four drafts of the comment overstated what was known, and review caught each.**
They said word count instead of characters, left H out, measured H only in its
hoisted best case, and quoted a per-hint band narrower than the data. The
measurements now live on #546 and nowhere else, so the comment carries the
bound and a pointer, not a log.
