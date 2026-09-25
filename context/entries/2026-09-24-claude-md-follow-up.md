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

Each trim keeps its instruction and moves only a record that D-079 or D-071 was
confirmed, by search, to hold.

**This matters for #559.** Main plus #559's +867 bytes would exceed 150,000 on
their own. With this change the pair fits, with roughly 500 bytes of headroom.

**Two trims were refused, because the cited record does not hold the text:**
- the subagent-citation arithmetic, "D-079 carries the arithmetic" (D-079 has
  none of it);
- the LEAVE-table percentages, cited to D-058.

The file's own trim list now says to confirm the cited record before cutting.
