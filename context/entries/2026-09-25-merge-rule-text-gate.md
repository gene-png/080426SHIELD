# 2026-09-25: a change to the merge rule's text is always red (interim, #572)

Branch `track1/merge-rule-text`, branch-start base `06fa7ce`. The owner's
decision, with his changes to the proposal on #572.

## Why

A PR can edit CLAUDE.md's merge rule and, under the rule as it then reads,
clear itself: CLAUDE.md is not a condition-5 path, and the rule's own
conditions are not listed anywhere it protects. Until CODEOWNERS covers the
governance files, the change is made VISIBLE instead.

## What changed

- **`check_merge_rule_text.py`** compares the `## The merge rule` section of
  CLAUDE.md (heading to `## Real commands`, which includes the condition-5
  path list) at the PR's merge base and at its head. Exit 0: byte-identical. 1:
  changed, with the changed lines named. 2: could not look (the section
  missing at either end, including a renamed heading; git cannot read a ref;
  CLAUDE.md missing; a bad argument). No label, no escape.
- **Its own job in `audit-gate.yml`**, "Merge rule text", with
  `fetch-depth: 0`. NOT a required check: that is the owner's setting.
- Fixtures for 0, 1 and 2 (a whitespace-only edit is the adversarial 1),
  range-mode unit tests against real repositories, and a
  `test_gate_crash_exit_code.GATES` entry.

## Proof

- Red on revert: a whitespace-insensitive compare, a missing section read as
  empty, the section running to the end of the file, and the head read at the
  base each turn a named test or fixture red.
- Live, on 2026-09-25: this branch against `main` exits 0 (139 lines
  compared). #581, which adds the compose exception to condition 5, exits 1 and
  names its lines. That is the gate doing its job on a real PR.

## Limits

It enforces visibility, not a signature. It does not see a semantic change
outside the section (a cited D-record, an agent file, a gate's code). A PR
editing its own workflow step can neuter it until CODEOWNERS covers
`.github/workflows/` and the bot account exists (#572).

## After the first review (`6fcc02f`)

- **The start was pinned, at the base and at the head** (the end was not;
  see the second review below). There must be exactly
  one `## The merge rule` heading, and `### Condition 5: the paths` must lie
  inside its section; otherwise exit 2. Without that, a decoy copy above the
  real section was what got read, and a `## ` heading inserted above the path
  list ended the section early, so that later path-list edits compared green.
  Fixtures for the extra heading, the decoy and a missing subsection, each red
  on revert.
- **Bytes are compared.** `git show` output is decoded but not
  newline-translated, and file mode reads bytes, so a CRLF edit is a change.
  A test writes one at runtime (a CRLF fixture would be normalized by the
  repo's `eol=lf`) and checks the CR is printed as a visible `\r`.
- The job's `actions/checkout` and `setup-python` match the sibling jobs (`@v7`).
- The condition-1 count angle is on #584, not filed twice.

## After the second review (`2ae1650`)

- **What is pinned, stated exactly** (the first review's "pinned at both
  ends" overclaimed: only the start was). Checked separately in the base's
  CLAUDE.md and in the head's, each failure exit 2:
  - the start: exactly one `## The merge rule` heading;
  - the end: exactly one `## Real commands` heading, and it is the first `## `
    line after the start. Before this, a `## ` line anywhere below the
    subsection heading (inside the list, lower down, or at column 0 in a code
    fence) ended the section early and the text after it compared green;
  - the subsection: `### Condition 5: the paths` lies inside the section.
- **Range mode's byte fidelity is tested**: a CRLF-only commit in a tmp repo
  with no `.gitattributes` and `core.autocrlf` off exits 1.
- Fixtures added for a heading directly under the subsection, a column-0
  `## ` in a fence, and a decoy below the real section. The earlier
  heading-above fixture now fires on the terminator check, and its needle says
  so.
- Red on revert, six mutations, each red on its named tests or fixtures: the
  start count, the subsection check, the terminator identity, the terminator
  count, a universal-newline file read, and `_git` with `text=True`.
