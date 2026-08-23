<!--
Delete any section that does not apply. The Adversarial audit block is the one
exception: on a PR touching code it is REQUIRED, and the check that enforces it
("Adversarial audit recorded") reads these literal lines. Prose describing an
audit is explicitly not enough.

Code, for that check, means anything that is not a .md/.txt/.rst file, plus
CLAUDE.md, this template, and anything under .claude/ -- but MINUS anything under
docs/ or context/, which are exempt whatever their extension. A docs-only PR is
exempt from the CHECK and still wants the reviewer -- see CLAUDE.md, "Rules of
the road".
-->

## Summary

<!-- What changed and why. One paragraph; the task table below carries detail. -->

## Changes

| Change | Where |
| ------ | ----- |
|        |       |

## Adversarial audit

Findings:
Disposition:
Scope:

<!--
Run .claude/agents/adversarial-reviewer.md BEFORE opening this PR, and again
after any substantive change to the branch, so findings land here rather than as
a follow-up.

  Findings -> 3
  Disposition -> 2 fixed here, 1 filed as #NNN.
  Scope -> the 4 files in this diff, at <sha>

Keep each value on the SAME LINE as its label. Answering underneath does not
match, and the check then reports 'no "Findings:" line' over a body that visibly
contains one -- a message that is false about your own text.

`Scope` is not enforced by the check and is the line that makes `Findings: none`
falsifiable: a reviewer pointed at a stale tree, the wrong branch or a subset of
the diff returns a clean report that is true about what it saw and false about
this PR.

If it could not run, say which and do not write "none" -- that is a claim about
the code rather than about the process:

  Findings -> not run - reviewer absent
  Disposition -> blocked on tooling; <named human> approved shipping without it.
  Scope -> n/a

(Also valid: `erroring`, `timed out`, `not dispatched: <what conflicted>`.
Never "none" when it did not run -- "none" is a claim about the code.)

Never substitute a self-audit. The check cannot tell the difference, which is
the whole reason the rule is written down.
-->

<!--
The examples above deliberately use "->" instead of a colon. The check does NOT
strip HTML comments (see the open issue about a commented body satisfying it),
so a commented-out "Findings: 3" would satisfy the gate from inside this
template -- every PR would pass having recorded nothing, invisibly. Do not
"correct" the arrow to a colon.
-->

## Test plan

<!-- What you ran, and what it said. "Tests pass" is not a test plan. -->

## Known follow-ups

<!-- Anything filed rather than fixed, with issue numbers. Write `filed as #NNN`
or `see #NNN` -- a closing keyword beside a live number closes that issue, and
the "No accidental issue closes" check will reject the PR. -->
