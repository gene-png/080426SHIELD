# 2026-09-24: CLAUDE.md carries the owner's settled decisions, and pays for them

Branch `track1/claude-md-follow-up`, base `20f747f` (after #539).

## Why

These are decisions the owner has already made and kept being asked about. Once
written down, they are applied instead of asked. #539 already carried the
delivery-path rule and the consultant-is-a-path clarification.

## What changed

- **The #528 sentence is widened.** The scale has no term for "any consequence
  that is not a wrong number", not only a compliance one: #53, #551, #552 and
  #546.
- **The `\s+` rule-class line.** Literal names match `\s+`; shape rules match
  `_HSPACE`. It is a rule-class difference, not an inconsistency (D-088).
- **The three-value CHECK**, at the owner's instruction, placed where a reader
  designing a status or a deliverable figure meets it. The 2026-09-24 misses:
  - Partial carried no reason (#554);
  - N/A had no acceptance disposition (#557);
  - the coverage percentage had no "unverified" (#554).
- **"Gate the release, not the click"**, backed by **D-089**, which records
  #557's B6 dispositions: `not_applicable` / `accepted` / `keep`; the owner
  field supplied by the client; bulk apply blocked for `accepted`; and owner and
  date required at release, not at the click.

## Paid for, under the size gate

The file shrank by roughly 770 bytes net. The trims:
- the merge rule's position story, which was told twice;
- the final section's rationale;
- the stash-archive PowerShell explanation.

Each trim was meant to keep its instruction and move only a record that D-079
or D-071 held. **That certificate was false for the stash trim**, and the
adversarial review caught it: the "no PowerShell equivalent, deliberately"
sentence is in no record, and dropping the "run in PowerShell 5.1 on
2026-09-08" date left a dateless negative claim. Both are restored.

**This matters for #559.** The pair must fit under the size gate together. Run
`check_claude_md_size.py` on the merged pair; do not trust a figure written
here.

**Two trims were refused, because the cited record does not hold the text:**
- the subagent-citation arithmetic, "D-079 carries the arithmetic" (D-079 has
  none of it);
- the LEAVE-table percentages, cited to D-058.

The file's own trim list now says to confirm the cited record before cutting.

**After review, the false pointers themselves are removed**, not only left
untrimmed. Five named text their record did not hold: those two, plus three
more into D-079 (the correction-paragraph list, the numbers-in-prose instances,
and the verification-sentence rule). Leaving them while the trim list called
them false was a self-contradiction. D-079's other pointers were checked and
hold. The pointer beside the merge-rule measurement table is #559's to fix.
