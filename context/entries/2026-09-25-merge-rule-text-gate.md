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
  CLAUDE.md (heading to the next `## `, which includes the condition-5 path
  list) at the PR's merge base and at its head. Exit 0: byte-identical. 1:
  changed, with the changed lines named. 2: could not look (the section
  missing at either end, including a renamed heading; git cannot read a ref;
  CLAUDE.md missing; a bad argument). No label, no escape.
- **Its own job in `audit-gate.yml`**, "Merge rule text", with
  `fetch-depth: 0`. NOT a required check: that is the owner's setting.
- Four fixtures (0, 1, 2, and a whitespace-only edit as the adversarial 1),
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
