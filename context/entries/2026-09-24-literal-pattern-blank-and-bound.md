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
question closed. The results, on 1 MB of text with one hint:

- A whitespace run between two occurrences of a hint, or inside one, is linear
  in the text.
- A hint of k whitespace-separated tokens costs O(k × T), where T is the text
  length. The scan pays it, because each `\s+` join makes a near-miss run to
  the hint's last token. The per-position loop pays it too, because inside a
  region every position can start a full match.
- The reachable worst case is k = 128: every hint and legal name comes from a
  255-character column. That measured about 1.6 µs per character on main,
  against 8.5–254 ns per character for the pre-#542 pattern on the same text.

The comment above the loop in `_redact_names` carries the numbers. It also
says the bound depends on those column caps, and that a hint source without
one lifts it.
