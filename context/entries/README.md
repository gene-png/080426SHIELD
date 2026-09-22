# `context/entries/` — one file per landing entry

**Add a NEW file here. Never edit an existing one, and never add an index.**

Naming: `YYYY-MM-DD-<short-slug>.md`, dated the day it lands, slug naming the
subject a reader would search for — an issue number is fine
(`2026-09-22-387-zt-disclosure.md`).

## Why this directory exists

`CONTEXT.md` is defined as "project status as of `main`", and every PR was
required to update it in the landing commit. Measured on 2026-09-22:
Of the last 10 first-parent commits on `main`, **8** touched `CONTEXT.md`; of
the last 25, 8; of the last 50, 10.

<!-- counted: for N in 10 25 50, count first-parent commits on origin/main whose --name-only lists CONTEXT.md, at 4a7e08f, 2026-09-22 -->

(An earlier version of this paragraph said "25 of the last 25" under a command
that could not have returned anything else — `git log -25 … -- CONTEXT.md` caps
its OUTPUT at 25 rather than selecting the last 25 commits. See D-081.)

Every branch therefore edited one file, at the same anchor, and every merge
invalidated the next branch's copy. Three consecutive PRs conflicted on it and
on nothing else, each costing a hand resolution whose only possible outcome was
"keep both" — a merge conflict raised over two paragraphs that do not interact.

**An append-only convention does not fix this**, which is why it was considered
and rejected: git conflicts on two branches adding lines at the same anchor
whether or not the additions are appends. That is exactly what the three
conflicts were.

**A generated index file would reintroduce it exactly**, which is why there is
none. An index is a second shared mutable file that every branch must touch, so
it would inherit the whole defect one level down. **The directory listing IS the
index**: filenames carry the date and the subject, and `ls` sorts them. That is
the derivation-over-synchronization rule applied to a document — a value that
cannot be out of sync beats one that merely is not, right now.

## What stays in `CONTEXT.md`

The sections that describe a CURRENT state rather than an event, and are
rewritten rather than appended: `## Current state`, the `mvp-blocking` mapping,
`## Machine-local facts`, `## Deferred / needs a human`, `## Test coverage
status`, and the `## Lessons learned` sections. Those are edited in place by
whoever changes the thing they describe, and two branches changing the same
current-state sentence SHOULD conflict — that is a real disagreement about what
is true, and resolving it by hand is the correct cost.

The dated `### YYYY-MM-DD — …` narrative sections already in `CONTEXT.md` stay
where they are. They are history and nothing appends to them any more. They move
here only if some other PR is editing that region anyway; migrating them as a
project is the large self-referential pass this repo has a rule against.

## What this does NOT change

Merge-rule condition 3 still binds: the record is updated in the LANDING COMMIT,
not afterwards. A fragment added here satisfies it. The condition was never
about one file — it was about the update not being deferred, and deferring it to
a later PR is the option that WAS rejected, because a record written after the
fact is written by someone who no longer remembers the measurement.

`check_recalled_counts.py` enforces this directory as well as `CONTEXT.md`, so
the numbers rules apply here unchanged. A fragment is not a lower standard; it
is the same standard in a file that cannot collide.
