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

## The cost, measured and written at the loop

The owner asked for one adversarial measurement before the performance
question closed. The results:

- A whitespace position is rejected at once. A whitespace run inside or
  between occurrences does not add a term of its own while it is no longer
  than the region it sits in.
- The cost is O(H × L × T). T is the text length, L the longest hint in
  characters, and H the number of hints sharing one anchor group, which is
  compiled as a single alternation.
  - Inside a region, every position where a hint could begin gets a match that
    compares up to L characters.
  - At each position, every alternative that fails pays for the prefix it
    matched first. The exception is a prefix that EVERY hint in the group
    shares: CPython's parser hoists it out of the alternation, so it is paid
    once. One hint that breaks the shared prefix restores the full H factor.
- **Three drafts of the comment understated it, and review caught each.**
  1. It said word count. A one-word hint of 255 dashes measured 1.4–1.6 µs per
     character.
  2. It left out H.
  3. It measured H only in the hoisted best case: 201–302 ns per character at
     H = 64. With one hint that breaks the prefix, H = 64 measured 31–33 µs
     per character, about 32 s per MB. That was in the api image, Python
     3.12.13, over 200 KB of text.
- **L is bounded: 255 characters.** Hints come only from `display_name`, a
  255-character column, and email local parts, which `EmailStr` keeps under 254
  because it refuses any address over 254. That was measured in the api image
  with email-validator 2.3.0. An earlier draft said 318; it is wrong.
  `legal_name` goes to `redact_org_name`, which has no per-position loop. Its
  scan has the same L term, also bounded at 255.
- **At L = 255 with one hint**, over 1 MB and five runs per shape, the observed
  spread was 1.4–3.4 µs per character. The pre-#542 pattern measured 11–45 ns
  per character on the same shapes.
- **H is bounded by nothing.** Each user in a tenant contributes up to two
  hints, and users set their own display names. It is filed as #546 rather
  than capped here, because a cap on hints is a cap on what gets redacted.

The comment above the loop in `_redact_names` carries the observed sets and
both bounds.
