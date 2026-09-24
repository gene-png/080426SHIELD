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

- A whitespace run between two occurrences of a hint, or inside one, is linear
  in the text.
- A hint of L characters costs O(L × T), where T is the text length.
  - The per-position loop pays it: inside a region, every position where the
    hint could begin gets a match that compares up to L characters.
  - A near-miss makes the scan pay a similar term when the hint has many `\s+`
    joins.
- **The first draft of the comment said words, not characters.** The review of
  9021eb1 disproved it: a one-word hint of 255 dashes measured 1.4–1.6 µs per
  character.
- At L = 255, over 1 MB and five runs per shape, the observed spread was
  1.4–3.4 µs per character. The pre-#542 pattern measured 11–45 ns per
  character on the same shapes.
- The reachable limit is L = 318, not 255. Display names and legal names are
  255-character columns. But an email local part is bounded only by the
  320-character `User.email`, because `EmailStr` does not enforce the
  64-character local-part limit (65 was accepted). L = 318 was not measured;
  the cost scales with L.
  - An earlier figure of "1.6 µs worst case" was a single best-of-three reading
    and understated the spread.

The comment above the loop in `_redact_names` carries the observed sets. It
also says the bound depends on those column caps being in characters, and that
a hint source without one lifts it.
