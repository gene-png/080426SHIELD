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

So the drop keys on a column-0 whole-line comment, not on position, and a
plain line in the same position survives. What this cannot show is the new
final line itself being injected: that needs a session that reads `CLAUDE.md`
from `main` after this merges. Check it then, and reopen #459 if
`CLAUDE-MD-CANARY: v2` is missing.

## Limit

Other whole-line HTML comments in `CLAUDE.md` (for example column-0
`<!-- counted: ... -->` provenance markers) are dropped from injected copies
in the same way. That hides provenance from agents, not a rule, and is left
to #459's comments rather than changed here.
