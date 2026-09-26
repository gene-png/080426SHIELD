# 2026-09-25: the CLAUDE.md canary is plain text, so injected copies carry it (#459)

Branch `track1/canary-survives-injection`, branch-start base `2028f38`.

## Why

The canary was `<!-- CLAUDE-MD-CANARY: v1 -->`, a whole-line HTML comment.
Context injection drops a comment that stands on its own line (the comments
on #459 record the witnesses; indented and inline comments survive). So every
injected copy of `CLAUDE.md` ended one line early, and step 0a, obeyed
literally, stopped every agent on a whole file. A control that fires on every
correct read gets ignored, and then the one real truncation reads as the
known false positive.

## What changed

- The marker is now the bare line `CLAUDE-MD-CANARY: v2`, in `CLAUDE.md` and
  in the step-0a instruction at its top and in all three agent definitions.
  The version moves to v2 so an instruction and a marker from different eras
  cannot silently agree.
- `check_claude_md_size.py --require-canary` requires exactly that line last.
  A marker wrapped in an HTML comment, or the older version, is exit 2 naming
  that cause, not "no canary". A test pins that the constant contains no
  comment delimiters.
- A fixture for the #459 shape (the v1 comment as the last line, exit 2).

## What was measured, and what was not

Measured on this session's own injected `CLAUDE.md` (main at `2028f38`,
2026-09-25), against the file on disk:

- `CLAUDE.md` on `main` has exactly two column-0 whole-line HTML comments:
  line 230 (`<!-- counted: condition 5's path list ... -->`) and the canary,
  line 2336 (`grep -n "^<!--"`). BOTH are absent from the injected copy.
- The plain lines around each survive. The table row above line 230 and
  the paragraph below it are both present, and the plain prose line directly
  above the old canary is the injected copy's last line.
- Indented comments survive, for example `  <!-- counted: historical -->`.

That v2 survives rests on the comment-stripping HYPOTHESIS, not on a
measurement of the new line: what the evidence shows is that whole-line
column-0 HTML comments vanish WHEREVER they sit, not only at the end. Besides
the canary, line 230 on `main` vanished from this session's injected copy,
and a reviewer's injected copy of the primary tree lost its line 2287, also a
column-0 comment mid-file. Plain lines beside each survived. The new final
line itself can only be seen by a session that reads `CLAUDE.md` from `main`
after this merges. That check is recorded in the PR body and as a comment on
#459, and this PR does NOT close #459, so the check has a live home.

## Limit

Other whole-line HTML comments in `CLAUDE.md` (for example column-0
`<!-- counted: ... -->` provenance markers) are dropped from injected copies
in the same way. That hides provenance from agents, not a rule, and is left
to #459's comments rather than changed here.

## After the first review (`cba5455`)

- The "wrapped or older" refusal is decided from the LAST non-empty line
  only. It tested every line, and `CLAUDE.md` names the marker in its own
  top-of-file notice, so a deleted final marker read as "wrapped" and the
  no-marker branch was unreachable on the real file. A test with the notice
  and no final marker pins "has NO canary marker".
- The survival claim is reworded as resting on the comment-stripping
  hypothesis, with its evidence; the post-merge check is on #459, which this
  PR leaves open.
- D-079's canary paragraph is date-qualified in place (a present tense gone
  stale, not a changed decision), and "three refusal branches" is now four
  there and in the gate's docstring.

