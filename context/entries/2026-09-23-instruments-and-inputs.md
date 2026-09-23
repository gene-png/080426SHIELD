# 2026-09-23 — two instrument findings, kept OUT of CLAUDE.md on purpose

These were written into `CLAUDE.md` first, into the "prefer the most primitive
available signal" section, and then taken back out. The reason is the finding
below, and it is the more useful of the three.

## Why they are here and not there

`CLAUDE.md` is 149,144 bytes against a 150,000-byte hard gate. The two lines came
to **617 bytes**, leaving **239** — and `CLAUDE.md` is where the merge rule lives.
**D-079** records that file being unreadable from 2026-09-10 to 2026-09-22 because
it exceeded a reader's limit, and the consequence was that the rule deciding
whether agents may merge unattended was invisible to the agents it governs.

Adding a true, well-argued instrument note to that file is exactly how it got
there. D-081 exists for entries like this. So: nothing further goes into
`CLAUDE.md` until something comes out of it.

## Instrument finding: `gh`'s `MERGEABLE` answers a two-dot question

It belongs in `CLAUDE.md`'s instrument table as another row, and is recorded here
instead:

| Read | Should have read |
| --- | --- |
| `gh`'s `MERGEABLE` on two PRs | whether they conflict with EACH OTHER |

**Measured 2026-09-23.** #469 and #470 each report `MERGEABLE`/`CLEAN` against
`main`, merge cleanly against `main` independently (41 and 26 files staged), and
**conflict with each other** on `apps/api/tests/unit/test_gate_crash_exit_code.py`
— both append their new gate to the same registry list. GitHub answers "does this
branch merge into main"; the question that decides whether two green PRs can both
land is "do these two branches merge into each other", and nothing on either PR
page asks it.

Still true after both branches were rewritten and re-pushed (`7a3551e`,
`7f32c7f`). `CLAUDE.md` already says to run the pairwise merge when two open PRs
touch one file and to say which pairs you checked; what this adds is that the
instrument people actually read reports the wrong proposition confidently.

## The root under three of tonight's findings

**A TEST WHOSE INPUT WAS CHOSEN BY THE THING UNDER TEST.** Instances from one
night, from three different authors' work:

1. **A mutation drawn from inside the region the tests already cover.** The
   expected value is sampled from the covered set, so the probe cannot reach the
   uncovered one.
2. **An allow-list validated only against benign traffic.** #469's guard was
   certified by "all four open bot PRs pass" plus one planted
   `continue-on-error` — a line entirely outside the admitted language. It
   established that the guard refuses obviously foreign content and never tested
   whether the admitted language is narrow. Three real holes lived inside it, all
   at exit 0.
3. **A Postgres fixture hand-seeded with the one spelling the filter under test
   already agreed with.** #209's `services.kind` filter keyed on the enum VALUES;
   the column stores the NAME. I inserted the row myself, using the value
   spelling, and the filter agreed with the one input I wrote. Three SQLite tests
   caught it in seconds; the Postgres run did not, because I made its rows.

Each produces a confident green from a population that could not have gone red.
**Ask where the input came from before reading the result.**

A fourth arrived the same day from the reviewing side: a human-author probe
hardcoded the bot login into its harness, so it answered "what does a bot PR do"
while the question was "what does a human PR do", and returned a clean confident
number for the wrong question.

## The thing neither of these fixes

`SOFT_LIMIT_BYTES = 135_000` and the file is 14,144 bytes above it, so the soft
warning is **permanently lit**. A warning tier that is continuously on is not a
warning tier — nobody has read it as information in weeks, which is why 239 bytes
of headroom arrived without anyone noticing the approach.

**Recommendation, not taken unilaterally because it is a governance call:** do
NOT move the soft limit to a currently-green value. It is telling the truth — the
file IS over budget and the documented trims ARE due. Raising the line would
silence a true signal, which is the same move as widening a gate to clear its
first red. What is broken is that nothing acts on it. The hard limit must not
move either; the script already refuses a flag that raises it, which is right.

Filed separately so it is somebody's decision rather than a paragraph.
