# Conditions 4 and 5 are computed from the diff now, not remembered

The merge rule says a PR tripping 4, 5 or 6 comes back to the human, and calls
condition 5 "mostly a path match". A path match with an exact answer, decided
from memory by whoever wants to merge, is an invitation to get it wrong in the
direction that suits you — and that is the failure that actually happened,
repeatedly, in bodies reading "trips nothing" over diffs that tripped three
things.

`apps/api/scripts/check_merge_rule_conditions.py` computes both and compares
them against what the body claims.

## What it enforces is HONESTY, not abstention

The first design refused a PR for tripping a condition. That is wrong: condition
5 is tripped by most code PRs here — 13 of the last 15 merges by the rule's own
measurement — so a gate reddening on it would be red on nearly every PR, and a
routinely-and-correctly ignored rule teaches that the rules are advisory, which
is expensive for the ones that are not. A permanently red required check trains
people to merge past red.

So a body naming every computed condition passes. A body omitting one fails,
printing the paths and why each is gated.

## Condition 6 is deliberately NOT computed

"Nothing that changes deliverable content, exporter output, or client dashboard
numbers" is a judgement about what a change MEANS. A touched exporter might be a
comment; a `lib/dashboards/` edit can alter a rendered number without touching a
listed path. The rule already calls 2, 3 and 6 self-attested, and this leaves 6
exactly as honest as it was rather than pretending a glob decided it.

## The gate set is derived

`derived_gate_paths` runs the membership test the rule states — *does any
workflow execute it as a gate* — over `.github/workflows/`, so a gate wired in a
spelling this file has never heard of still counts. It converts the dotted
`python -m scripts.x` form to a path, because a diff never names the dotted form
and a set holding it would match nothing, silently. That is the miss the
published version of that grep in `CLAUDE.md` had.

## Self-application found a real hole, and it is the best thing here

Run against its own one-file PR, the gate reported **"clean — none of 1 changed
path(s) trips condition 4 or 5"** over a new gate script.

`EXPLICIT_CONDITION_5` had omitted `apps/api/scripts/check_*.py`, on the belief
that the derived set subsumed it. It does not, and the distinction is the
lesson: **the derived set answers "is this EXECUTED as a gate today", and a gate
not yet wired into a workflow is not.** The rule names that glob explicitly;
dropping it because a derivation looked like it covered it is the half-sweep
shape. No amount of re-reading the table would have found it — running the gate
on itself did, in one command.

## Two more caught by existing harnesses, on the first run each

- `test_gate_crash_exit_code.py` — the crash handler omitted
  `KeyboardInterrupt`, so Ctrl-C came back as exit 2, telling an operator who
  knows exactly what they did that the gate could not look. That harness doing
  its job on the newest gate in the repo.
- `check_gate_fixtures.py` — refused an exit-2 fixture with no
  `stdout_contains`, because a gate has several could-not-look branches and the
  code alone cannot say which fired. That is the rule I had written into this
  gate's own docstring, enforced against me by a harness I did not write.

## Not registered as a required check, and that is a decision

It runs as its own job so a merge-rule failure does not report as *"Adversarial
audit recorded"* failing — a different question gets its own check. It is **not** added to
branch protection: that is a GitHub setting a PR cannot change, and doing it
would make condition 1's "all seven CI checks green" read eight, which the rule
says to re-derive rather than let drift. So it reports, visibly, on every PR,
and registering it is a separate decision with its own cost.

## Silent-success branches, enumerated before the first line

Empty changed-file list, missing or unreadable input, an unknown flag, no repo
root above the script, and a derived set that comes back empty — all exit 2.
Only "no gated path touched" exits 0, and its message states how many paths it
read so a reader can tell it from the others.

## 2026-09-23 — NARROWED TO CONDITION 4, and the condition-5 half withdrawn

Everything above describes a gate computing conditions 4 AND 5. Adversarial
review found defects that are design rather than patch, so condition 5 was
withdrawn and filed as **#478**.

**The derivation could not see `scripts/web-install-if-stale.sh`.** That is the
web install guard — named in `CLAUDE.md` as a reason `docker-compose.yml` is a
condition-5 path, the thing that decides whether a lockfile security bump reaches
the running container (#226), and gated by `tests/gates/web_install_guard.sh`. It
hid three ways at once: the derivation opened only `.github/workflows/`, the verb
is `sh` rather than `bash|python`, and the operand is the container path
`/app/web-install-if-stale.sh`. Any one would have hidden it.

**That was a regression against a fix this repo had already made.**
`check_gate_fixtures.py::invocation_text` takes compose files as `extra` because
reading only the workflows directory was, in its own words, "a live FALSE
POSITIVE, not a latent one". The new gate read the narrower surface the sibling
gate had been corrected away from.

**And the acknowledgment matcher could not tell an acknowledgment from a
denial.** `## Merge rule` + "This does not trip condition 5." passed. That is the
closing-keyword defect `CLAUDE.md` records — "THE NEGATION IS INVISIBLE TO THE
MATCHER" — rebuilt inside the gate whose subject is honesty. Two more ways it
passed a body acknowledging nothing: the PR template has no `## Merge rule`
heading so the region fell back to the whole body, and the template's own
commented `the 4 files in this diff` carries a bare `4`; and any sha, version,
ordered-list item or changed path with an isolated digit did it too.

**So the acknowledgment is a MARKER now**, the same shape as
`Auto-close-approved:` and for the same reason:

    Merge-rule-condition-4: <what the migration does>

A denial cannot produce it, the template does not contain it, and an empty reason
is refused — the rule `check_test_integrity` applies to `# test-integrity:`.

**The test named for the derived half never exercised it.** Its input
`apps/api/scripts/check_decision_numbers.py` matched the EXPLICIT glob, and the
lookup tried the table first and `break`ed. Replacing `_as_path`'s body with
`return raw` would have left the suite green. Recorded in #478, because whatever
replaces this needs a derived-ONLY input or it inherits the hole with a suite
that says otherwise.

### What the narrowed gate is

Condition 4: one glob (`apps/api/alembic/versions/*.py`) with an exact answer.
`alembic/env.py` is deliberately NOT condition 4 — the merge rule puts it under
condition 5 in as many words — so it is unenforced by this gate, which the
docstring says rather than leaving silently true.

| check | result |
| --- | --- |
| `pytest tests/unit/test_merge_rule_conditions_gate.py` | 18 passed |
| `check_gate_fixtures.py` | 42 cases across 9 gates behaved as specified |
| `ruff` / `black` / `prettier` | exit 0 |

The fixture set kept the control and the empty-list case, dropped four
condition-5 cases, and gained three adversarial ones: a denial, the PR template's
boilerplate, and a declared migration passing with its reason echoed.

### Whether condition 5 should be mechanised at all

Left open in #478 rather than assumed. The merge rule's own measurement is that
13 of the last 15 merges trip it, so a blocking gate would be red on nearly
everything — and `CLAUDE.md` records what a routinely-and-correctly-ignored rule
teaches. An informational report that never blocks, or a marker declaration of
condition 4's shape, are the honest options. The regex is not the first thing to
fix.
