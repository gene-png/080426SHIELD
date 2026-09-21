#!/usr/bin/env python
"""Prove every gate CAN FAIL -- not merely that it runs and prints something.

WHY THIS EXISTS. This repo keeps producing checks whose inputs cannot
distinguish their pass state from their fail state (#213). The check runs, goes
green, and the green means nothing, because no input it actually saw could have
made it red. Recorded instances: a predicate enumerating HEAD/index/tracked
files that therefore excluded `git stash drop`, the operation that prompted it;
a duplicate-D-number regex collapsing `D-059a` into `D-059`; a dashboard suite
in which every fixture seeded a state where the two candidate fields coincided;
`git stash show --stat` accepted as proof of archive recovery when it cannot
display a `-u` stash's untracked parent at all.

`CLAUDE.md` already carries the half-rule -- "a guard must be observed in BOTH
states before it is trusted" -- and it has been losing, because it is a habit
that fires only when someone remembers to ask. This makes it mechanical.

## The contract

Every gate under `apps/api/scripts/` is either covered by fixtures here or named
in DEFERRED with a reason. A covered gate must have:

  * at least one case the gate PASSES (exit 0);
  * at least one case the gate FAILS with exit 1 -- the NEGATIVE CONTROL, without
    which the suite proves the gate runs and not that it discriminates. A 2 does
    not satisfy it: 1 and 2 are the codes D-051 exists to keep apart;
  * at least one case expecting exit 2, so the fail-closed half is covered too,
    and it carries `stdout_contains` -- a gate has several "could not look"
    branches and the code alone cannot say which one fired;
  * at least one case marked `adversarial`: input a reasonable person would
    expect to pass, that must not. Ordinary cases test the rule; adversarial
    cases test the boundary, and the boundary is where all of these have broken.

    IT IS THE ONLY ONE OF THE FOUR THAT LOOKS FOR INPUTS THE AUTHOR DID NOT
    ALREADY HAVE IN MIND. The other three are answerable from the code you
    just wrote: a pass, a refusal, a could-not-look. An adversarial case is
    answerable only by asking what someone ELSE would reasonably send. That
    asymmetry is why it is required rather than encouraged -- ordinary cases
    test what you thought of, which is the set that cannot contain the defect
    you are looking for.

    Measured, first time it was demanded of a gate that lacked one: writing an
    adversarial fixture for `check_decision_numbers` surfaced a live defect
    (#342) -- a subject REFERENCING another decision is flagged as naming one
    it does not add, which is an ordinary commit message here and reddens a
    PR. The fixture found it on construction, before it was ever run.

Every case names the INCIDENT it derives from, because a fixture derived from the
rule rather than from the failure is the inversion that produced the defects
above.

**What is mechanised is that the claim EXISTS; that it is TRUE is not, and
cannot be.** This file rejects a missing or whitespace-only `incident`. It cannot
tell whether the incident happened, whether the figures in it are real, or
whether it describes this fixture. Four incident fields in this corpus were found
inaccurate by an adversarial pass and corrected in `0ab309c` -- one claimed two
documents agreed on a figure where they give 11.5-17.5 and 12-18, one cited a
count that conflates three different populations, one described a two-line marker
as spanning three. Every one passed this gate.

That is the same scoping as the tier-1 claim below: form is mechanisable,
implication is not. Read "traceable incident" as a convention this file makes
visible, not a guarantee it enforces -- the enforcement is a reader.

## Fail-closed, per D-051

Exit 2 is "I could not look": fixture root missing, no gates discovered, a gate
directory with no cases, a malformed `case.json`, DEFERRED naming a gate that
does not exist. Exit 1 is "I looked and something is wrong": a gate returned the
wrong code, or its cases do not meet the contract above. Those must never share
a branch -- `check_audit_evidence`'s `is_code_change([])` printing
"documentation-only change, exempt" and exiting 0 is the recorded reason.

## What it does NOT do

It proves a gate CAN fail. It does not prove a gate asks the right question, and
nothing mechanical will -- see #213: form is mechanisable, implication is not.

**This gate cannot see itself.** It is excluded from its own discovery and is
covered by unit tests instead. That is the same shape `CLAUDE.md` records for
`check_recalled_counts`, whose help text is a Python string its own pattern
never reads. Stated here rather than left to be discovered later.

Usage:  python apps/api/scripts/check_gate_fixtures.py [FIXTURE_ROOT]
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

# Gates knowingly without fixtures, each with its reason. A gate in neither this
# mapping nor the fixture tree FAILS the run: silence must not be how coverage
# quietly shrinks.
DEFERRED: dict[str, str] = {
    # -- SHELL GATES (#318) -------------------------------------------------
    # They cannot be fixtured by this harness: `run_case` invokes
    # `[sys.executable] + argv`, and these are bash. Their both-states evidence
    # is INTERNAL -- each asserts a passing case and a refusing case of the
    # thing it guards -- and what this file now enforces for them is the half
    # that was actually missing: that a workflow INVOKES them. Both shipped
    # with neither, and ran nowhere for weeks.
    "prettier_hook.sh": (
        "Bash, so unfixturable by a harness that runs `[sys.executable] + argv`. "
        "Covers both states internally via `expect_ok` and `expect_refusal` "
        "against `--print-version`. The gap this harness now closes for it is "
        "wiring, not fixtures -- see `unwired_gates`. What is still NOT proved "
        "is that the gate itself can fail; `scripts/verify-in-worktree.sh`'s "
        "`--self-test` is the shape that would -- it appends a deliberate "
        "error, greps to prove the write landed, requires RED, then removes "
        "it -- and adding one here is filed rather than done. (An earlier "
        "version of this entry named a file that does not exist on this "
        "branch, sending whoever picks the work up to look for an exemplar "
        "that was not there.)"
    ),
    "web_install_guard.sh": (
        "Same as `prettier_hook.sh`: bash, internal both-states coverage, and "
        "the missing half was that nothing ran it. No `--self-test`, so a "
        "harness-cannot-fail defect in it would still be invisible."
    ),
    # -- #310's shell gate, a DIFFERENT incident from the two above ----------
    # It was WIRED from the day it landed -- `audit-gate.yml` runs it and its
    # `--self-test` on every PR -- so the "ran nowhere for weeks" history above
    # is not its history. What was missing here was this declaration: #327
    # landed the rule that every shell gate states its coverage, forty minutes
    # after #310 landed the gate, and each was green against a base that did
    # not carry the other. `main` was red on every PR until this entry existed.
    "close_guard_linked_file.sh": (
        "Bash, so unfixturable by a harness that runs `[sys.executable] + argv`. "
        "Its evidence is INTERNAL, and is the strongest of the three shell gates. "
        "It does not restate the workflow: it EXTRACTS the collect block out of "
        "`audit-gate.yml` by markers, refusing with exit 2 unless it finds "
        "exactly one, so it goes red when a workflow change breaks the anchor or "
        "the behaviour -- rather than agreeing with a copy of itself forever. It "
        "then stubs `gh`, drives the REAL close guard, and asserts the VERDICT in "
        "three states -- the query fails, the query returns nothing, the query "
        "returns numbers -- because the file's presence only matters through what "
        "the guard does with it. "
        "It is also the only shell gate here carrying a `--self-test`, which runs "
        "THREE mutations (`prefix`, `donothing`, `alwayspublish`), each pinned to "
        "an exact expected failure-label set. That shape is the entry's real "
        "content: the first version applied ONE mutation and accepted any "
        "non-zero, and under `prefix` alone only the two assertions of the first "
        "state go red -- so five of the seven labelled checks had been shown able "
        "to fail exactly never. (The script's own comment says 'four of the six'; "
        "it enumerates seven labels and omits one. Its count, not this entry's -- "
        "tracked rather than corrected here.) "
        "TWO limits, stated because the sentence above certifies strength and a "
        "reader would otherwise take it as complete. Its own fail-closed branches "
        "-- `cannot find`, no interpreter, `EXTRACT FAILED`, all exit 2 -- are "
        "exercised by no mutation and no check, so this gate does not meet the "
        "exit-2 half that `_contract_failures` demands of a FIXTURED gate. And "
        "the other two shell gates above have no `--self-test` at all, so a "
        "harness-cannot-fail defect in either is still invisible. A coverage "
        "statement, not a clean bill of health."
    ),
    # -- #296's two gates, which were invisible to BOTH harnesses (#318) ------
    # Neither carried the crash-is-not-a-verdict handler nor a `GATES` entry,
    # so `discover_gates` could not see them and `test_gate_crash_exit_code`
    # did not run them -- and the "gates can fail" step was green BECAUSE of
    # the omission. Both now carry the handler, which is what puts them here.
    "check_decision_numbers.py": (
        "Its input is a GIT RANGE, not a path: `--base`/`--head` name refs, and "
        "`run_case` substitutes `{dir}` into argv and invokes the script with no "
        "repository around it. A fixture would have to build a repo per case, "
        "which is what `test_check_decision_numbers.py` does instead -- it drives "
        "`main()` against a real tmp repository. That FILE is the coverage this "
        "entry stands in for; the enumeration that used to stand here named four "
        "behaviours and went stale the moment a fifth was added, so it points at "
        "the file rather than counting it. "
        "WHAT IS STILL MISSING, because the entry claimed parity with the "
        "fixtured contract and did not have it. `_contract_failures` demands four "
        "things of a fixtured gate and this file met two: it had a 0 and a 1, its "
        "exit-2 case asserted the CODE and no message while `main` has TWO "
        "could-not-look branches, and it had no adversarial case at all. The "
        "exit-2 message is now pinned to the `git log` branch. The ADVERSARIAL "
        "case is still absent, and the reason is worth more than the gap: "
        "constructing one surfaced a LIVE defect in the gate -- a subject that "
        "REFERENCES another decision (`D-090 -- supersedes D-072`) is flagged as "
        "naming a decision it does not add, which is an ordinary commit message "
        "here and turns a PR red. Filed as #342, not fixed on this branch. "
        "One more branch was unpinned until this round: `if not added: continue`, "
        "the legitimate skip for a commit that amends an entry without adding a "
        "heading. Deleting those two lines left all fourteen tests green -- "
        "measured, not argued -- and one named test now goes red for it."
    ),
    "check_mount_matches_database.py": (
        "Needs a live Postgres and an alembic revision to compare against, "
        "neither of which `run_case` can supply -- it invokes a script with argv "
        "and a fixture directory. Covered by "
        "`tests/unit/test_check_mount_matches_database.py`. Its stated residual "
        "stands and is NOT covered here: two worktrees each numbering the next "
        "migration 0047 make the id match while the schemas differ, and the "
        "check prints agreement. That is filed against the gate, not against "
        "this registry entry."
    ),
    "check_disclosure_consumers.py": (
        "Its input is a REPO-SHAPED TREE, not a path: it needs a schemas "
        "directory, a web surface and an exporter, and `run_case` substitutes "
        "`{dir}` into argv and invokes the script with a flat fixture "
        "directory. Building that shape per case is what "
        "`tests/unit/test_disclosure_consumers.py` does instead -- which this "
        "entry POINTS AT rather than counting, for the reason the "
        "`check_decision_numbers.py` entry above gives. The count that stood "
        "here (THIRTEEN states) was already wrong when it was read. "
        "It meets the fixtured contract rather than standing outside it: a "
        "passing case, a NEGATIVE CONTROL (a disclosure nobody renders, exit "
        "1, asserting the message), a could-not-look case for every exit-2 "
        "branch `main` has (no repo above the start, an unparseable schema, a "
        "missing web surface, zero disclosure fields, a LEADING unknown flag, "
        "a TRAILING extra argument) EACH ASSERTING ITS OWN MESSAGE, and an "
        "ADVERSARIAL case -- a field rendered ONLY in an exporter, which a "
        "reasonable person would expect to fail a gate named for screens and "
        "must not, because the rule is 'a screen OR a delivered artifact'. "
        "That case was written because applying the issue's own sketch "
        "literally would have reported a defect over "
        "`zt.py::GapAnalysisResponse.unusable_target_codes`, which reaches the "
        "client's deliverable. "
        "THE MESSAGE CLAIM IS REPAIRED, NOT INHERITED. This entry said five "
        "could-not-look cases 'each exit 2 with its own message' while three "
        "asserted the CODE alone -- so three branches could have been rewired "
        "to any other cause, or collapsed into one, with the file green. The "
        "sentence was the coverage a reader checked instead of opening the "
        "file. The flag case was worse than unmessaged: it passed the flag in "
        "`argv[2]`, which is the ARITY branch, so the leading-flag guard had "
        "zero coverage and deleting it left the suite green. Both slots are "
        "now separate cases. "
        "WHAT IS NOT COVERED, stated because the entry above certifies "
        "strength: arm 2's failing half -- nothing renders the audit `details` "
        "payload generically -- has no case, because `AUDIT_RENDERER_EXEMPT` "
        "holds that state open until #351 lands. What IS covered now is that "
        "exemption's EXPIRY, and `EXEMPT_FIELDS`' expiry, both directions: a "
        "field that acquires a reader, and an arm-2 exemption still set once "
        "the renderer exists. When the exemption is deleted, the case proving "
        "arm 2 discriminates is owed."
    ),
    "leave_row_oracle.py": (
        "STRUCTURALLY unfixturable, which is a stronger reason than the one first "
        "recorded here. --check-registry takes no path: REPO_APP and TESTS are "
        "derived from __file__, and discover_tables() imports the matrix modules by "
        "name after a sys.path.insert. argv carries only the flag. There is no "
        "invocation that points this gate at a fixture directory, so covering it "
        "means changing the script rather than adding a case. The reason previously "
        "written here -- 'a stand-in redact.py plus stand-in truth tables' -- was "
        "shared with check_separator_classes, whose deferral did NOT survive review "
        "and is now fixtured; anyone rejecting that argument would have read this "
        "entry as the same rejected one and spent a session rediscovering the real "
        "blocker"
    ),
    "mutation_sweep.py": (
        "not a gate CI can fail on: mutation-sweep.yml carries continue-on-error on "
        "the job, with the comment 'A survivor is a question to answer, not a build "
        "failure. This job reports; it never blocks anything.' That is the binding "
        "fact. Two weaker ones were recorded here first and one was wrong -- it is "
        "schedule AND workflow_dispatch, not schedule-only, and the tee pipe is the "
        "least of the three. Carried in this universe because it follows the same "
        "0/1/2 convention and a developer running it by hand reads exit 1 as "
        "'surviving mutants'"
    ),
}

_SELF = "check_gate_fixtures.py"
_REQUIRED_KEYS = ("incident", "expect", "argv")

# What MAKES a script a gate in this repo: the crash-is-not-a-verdict handler.
# Every gate ends with it, no non-gate has it, and `test_gate_crash_exit_code`
# already uses this exact string as its own marker.
_GATE_MARKER = "crash != verdict"


def scripts_dir_for(root: Path) -> Path:
    """The scripts directory beside a fixture root at <api>/tests/gates."""
    return root.parents[1] / "scripts"


def discover_gates(scripts: Path) -> list[str]:
    """Every gate, DERIVED from the convention that makes a script a gate.

    A gate here is a script that returns 0/1/2 verdicts and therefore carries the
    crash-is-not-a-verdict handler. That property is IN THE FILE, so this notices
    a gate nobody told it about.

    Two enumerations preceded this and both were wrong. The first globbed
    `check_*.py` and could not see `leave_row_oracle.py`, a real CI gate whose
    name does not match -- the trap `CLAUDE.md` names explicitly. The repair was a
    two-name hand list pinned to a SECOND hand list in
    `test_gate_crash_exit_code.GATES`: two enumerations that catch drift between
    themselves while neither can notice the world grew. That is the same hole one
    level up, and `CLAUDE.md` is explicit -- prefer a derivation over a
    synchronisation.

    Rejected alternative, recorded because it looks right: deriving from the
    scripts the WORKFLOWS invoke. Measured, that returns 11 -- it picks up
    `seed_demo.py` and `fire_scheduled_triggers.py`, which CI runs and which are
    not gates. It answers "what does CI execute", not "what is a gate".

    Residual, stated rather than papered over: a gate written WITHOUT the handler
    is invisible here. That is a convention violation in its own right, and
    `test_gate_crash_exit_code` exists to catch it -- but only for gates already
    in its list, so a gate with neither the marker nor an entry is missed by both.
    Narrower than a hand list, not zero.
    """
    found: set[str] = set()
    for path in sorted(scripts.glob("*.py")):
        if path.name == _SELF:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if _GATE_MARKER in text:
            found.add(path.name)
    return sorted(found)


#: Shell gates live at `<repo>/tests/gates/*.sh` -- a different language, a
#: different directory, and invisible to `discover_gates` twice over (#318).
#:
#: `discover_gates` derives Python gates from a property IN THE FILE, which is
#: the stronger form. There is no shell equivalent of the crash-is-not-a-verdict
#: handler, so these are derived from LOCATION instead: that directory holds
#: gates and nothing else, which is the convention the two existing ones were
#: written to. Weaker, and stated as weaker -- a shell gate written somewhere
#: else is invisible here, exactly as a Python gate without the marker is.
_SHELL_GATE_SUFFIX = ".sh"


def repo_root_for(root: Path) -> Path | None:
    """The repo root above a fixture root, or None when it is out of reach.

    DERIVED by walking up for `.github/workflows` rather than counting
    directories. `root.parents[3]` was correct for a full checkout and raised
    `IndexError` inside the api container, which mounts `apps/api` at `/app` --
    so the fixture root is `/app/tests/gates`, which has three parents and not
    four. `CLAUDE.md` records that exact shape costing a whole pytest session
    (#314, a `parents[4]`), and this file reproduced it within the week.

    A count is a claim about where this file sits in a tree. The marker is a
    property of the tree itself, so moving either one cannot silently pick the
    wrong directory -- it can only fail to find one, which the caller reports.
    """
    for candidate in [root, *root.parents]:
        if (candidate / ".github" / "workflows").is_dir():
            return candidate
    return None


def shell_gates_dir_for(repo: Path) -> Path:
    return repo / "tests" / "gates"


def workflows_dir_for(repo: Path) -> Path:
    return repo / ".github" / "workflows"


def compose_sources(repo: Path) -> list[Path]:
    """Compose files at the repo root -- the OTHER place CI invocation is declared.

    GLOBBED rather than named, so a second compose file (an override, a CI
    variant) is read without anyone remembering to add it here. A hand list of
    one entry is an enumeration, and this file's whole subject is what those
    miss.

    Non-recursive on purpose: a compose file nested in a subdirectory is not
    what `docker compose up` at the repo root reads, so counting it would
    report a gate wired by a file CI never loads -- the quiet direction.
    """
    return sorted(p for p in repo.glob("docker-compose*.y*ml") if p.is_file())


def discover_shell_gates(shell_dir: Path) -> list[str]:
    """Every `*.sh` under the repo-root gate directory."""
    if not shell_dir.is_dir():
        return []
    return sorted(p.name for p in shell_dir.glob(f"*{_SHELL_GATE_SUFFIX}") if p.is_file())


def unwired_gates(gates: list[str], workflows: Path, extra: Sequence[Path] = ()) -> list[str]:
    """Gates no workflow invokes. THE POINT OF THIS FILE, reached from outside.

    A gate that runs nowhere cannot fail, which is this file's own thesis -- and
    fixture coverage does not detect it: `web_install_guard.sh` and
    `prettier_hook.sh` each shipped with real both-states assertions inside and
    no workflow, no CI step and no script invoking either (#318). They proved
    something to nobody, for weeks, and the only reason anyone noticed was a
    reviewer reading the PRs that added them.

    Matched on the gate's STEM, at a WORD BOUNDARY, against the workflow text
    with full-line comments removed.

      * the STEM, not the filename, because four of the nine Python gates are
        invoked as modules (`scripts.check_audit_evidence`, `-m
        scripts.check_test_integrity`) and never by their `.py` name. Matching
        filenames reports four live gates unwired -- measured on this tree.
      * a WORD BOUNDARY, because a bare substring test reports a gate wired
        whenever its stem is contained in another word. `check_plan` would be
        satisfied by `check_plan_totals`, which CI does run; `prettier.sh` by
        the word `prettier` anywhere in `ci.yml`. No stem on this tree is a
        substring of another, so that was LATENT rather than live -- but it is
        the SILENT direction (a gate that runs nowhere reported as wired, which
        is #318 one naming collision later), where the false-positive direction
        it replaces is loud and gets investigated inside one run.
      * comments stripped, and this one is PROPHYLACTIC rather than measured.
        An earlier version of this docstring said it was "measured on this
        tree, because `audit-gate.yml` mentions `leave_row_oracle` in a comment
        ABOUT a gate it does not run". Wrong file and wrong conclusion:
        `audit-gate.yml` contains no occurrence of `leave_row_oracle` at all;
        the prose mention is in `ci.yml`, which ALSO runs that gate on a real
        uncommented step. So stripping changes zero verdicts on this tree, and
        no gate here is named only in comments. It stays because a mention read
        as an invocation is the substitution this file exists to refuse, and
        `test_a_gate_named_only_in_a_comment_is_unwired` is what stops someone
        deleting it.

    THREE residuals, stated because the first version of this docstring
    disclosed only the first and a reader would have taken that as the set:

      * an inline TRAILING comment is not stripped, so a stem appearing only
        after a `#` on a value line still counts as wired.
      * "a workflow invokes it" includes a workflow that never runs on a PR.
        `mutation-sweep.yml` is schedule-plus-dispatch only and carries
        `continue-on-error` on the job, so a gate named only there is wired by
        this check and unable to fail a build. The `mutation_sweep.py` DEFERRED
        entry states that about itself; this function did not.
      * only `.github/workflows/*.y*ml` is read. A composite action or a
        reusable workflow is never opened. There is no `.github/actions`
        directory on this tree, so that is latent -- and it fails LOUDLY when
        it arrives, reporting a wired gate as unwired.
      * a stem that is an ordinary WORD still matches wherever that word
        appears. The boundary closes `check_plan` inside `check_plan_totals`;
        it does not close a hypothetical `prettier.sh` against `ci.yml`'s
        `prettier@3.9.6`, because `@` is a boundary. Measured, not reasoned:
        `unwired_gates(["prettier.sh"], workflows)` returns `[]` on this tree.
        Naming a gate after a tool the workflows already mention is the way in,
        and the remedy is the name, not the matcher.
    """
    text = invocation_text(workflows, extra)
    return [g for g in gates if not mentions(text, Path(g).stem)]


def invocation_text(workflows: Path, extra: Sequence[Path] = ()) -> str:
    """The non-comment text of everything that DECIDES WHAT CI EXECUTES.

    Factored out so `unwired_gates` and `undiscovered_gates` share ONE
    definition of what counts as an invocation. They ask opposite questions
    over different populations -- "which of these gates is unmentioned" versus
    "which mentioned script is not a gate" -- so a shared matcher is a common
    definition rather than a mirror. Two copies of this stripping would let the
    two answers disagree about the same file.

    `extra` is what makes the surface correct rather than merely plausible.
    Reading only `.github/workflows` was a live FALSE POSITIVE, not a latent
    one: `check_mount_matches_database.py` is invoked by `docker-compose.yml`,
    on the line `python scripts/check_mount_matches_database.py &&`,
    immediately before `alembic upgrade head` -- exactly where that gate's own
    docstring says it belongs. The e2e and demo jobs both `docker compose up`,
    so it runs on every CI run of either. It was reported unwired the moment
    #338's marker put it in the registry.

    Wiring it into a workflow to clear that report would have been a
    certificate over the wrong proposition: CI starts from fresh volumes, so
    the stale-mount state the gate detects cannot arise there and a CI
    invocation could only ever pass. The gate was right, its placement was
    right, and the CHECKER's notion of "invoked" was too narrow.

    Residual, unchanged in kind: a gate invoked from a file named in neither
    the workflows glob nor `extra` -- a composite action, a Makefile, a script
    calling a script -- still reads as unwired. That direction fails LOUDLY,
    which is how this one was found.
    """
    lines_kept: list[str] = []
    for path in [*sorted(workflows.glob("*.y*ml")), *extra]:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").split(chr(10)):
            if not line.lstrip().startswith("#"):
                lines_kept.append(line)
    return chr(10).join(lines_kept)


def mentions(text: str, stem: str) -> bool:
    r"""Whether the workflow text names `stem` at a word boundary.

    The boundary rationale is in `unwired_gates`, and `(?<!\w)` rather than
    `\b` because a stem is invoked as a dotted module path
    (`scripts.check_audit_evidence`) as often as by filename -- `\b` after a
    `.` rejects those and reports four live gates unwired. Measured.
    """
    return re.search(rf"(?<!\w){re.escape(stem)}(?!\w)", text) is not None


#: Scripts a workflow runs that are NOT gates, each with its reason. The set is
#: small and each entry is a claim someone can check by opening the file --
#: same shape as `DEFERRED`, and for the same reason: an unexplained absence is
#: how coverage shrinks in silence.
NON_GATE_SCRIPTS: dict[str, str] = {
    "seed_demo.py": (
        "Populates the demo tenant for the e2e and demo jobs. It has no verdict "
        "to give -- it either seeds or raises -- and `CLAUDE.md` records it "
        "exiting 0 while deliberately skipping, which is the opposite of a gate."
    ),
    "fire_scheduled_triggers.py": (
        "A scheduled job that performs work. Nothing about its exit status is a "
        "judgement on the tree."
    ),
}


def undiscovered_gates(scripts: Path, workflows: Path, extra: Sequence[Path] = ()) -> list[str]:
    """Scripts CI RUNS that carry no gate marker and are not declared non-gates.

    THE THIRD ORACLE, and it exists because the other two cannot see this case.

    `discover_gates` derives gates from a marker IN THE FILE;
    `test_gate_crash_exit_code.GATES` is a hand list. A test comparing those two
    catches drift BETWEEN them and is blind to a script missing from BOTH --
    which is not hypothetical: it is exactly what #296's two gates were, and the
    registry check passed BECAUSE the thing it should have found was not in the
    registry. `discover_gates`'s own docstring states that residual; this
    narrows it rather than restating it.

    The signal is independent of the marker: a workflow INVOKING a script is
    evidence someone treats it as CI-significant, and it is written in a
    different file by a different hand. So a script CI runs is either a gate
    (marker present), or declared here with a reason, or a finding.

    MEASURED on `main` at b516891, which is where the defect was live: this
    returns `check_decision_numbers.py` -- one of #296's two gates, invoked by
    `audit-gate.yml` and in neither Python registry. The version of this file
    that shipped before #338 could not see it.

    HALF, and stated as half. `check_mount_matches_database.py` -- the OTHER of
    #296's two -- is invisible here, because no workflow invokes it at all. It
    is caught by `unwired_gates` instead, and only once its marker puts it in
    the registry. Two arms, two different blind spots, and neither alone covers
    #296.

    Residuals, inherited from `mentions` and worth naming where they bite
    differently in this direction: a script named only in a stripped comment
    reads as not-invoked here, which is the QUIET direction -- a real gate
    mentioned only in prose goes unreported. And a script whose stem is an
    ordinary word reads as invoked wherever that word appears, which is loud
    and gets investigated.
    """
    text = invocation_text(workflows, extra)
    out: list[str] = []
    for path in sorted(scripts.glob("*.py")):
        if path.name == _SELF or path.name.startswith("_"):
            continue
        if path.name in NON_GATE_SCRIPTS:
            continue
        try:
            body = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if _GATE_MARKER in body:
            continue
        if mentions(text, path.stem):
            out.append(path.name)
    return sorted(out)


def load_cases(gate_dir: Path) -> tuple[list[dict], list[str]]:
    """Return (cases, problems).

    A malformed case is a PROBLEM, never a silent skip -- a fixture the harness
    cannot read is the harness not looking, which is exit 2 and not exit 0.
    """
    cases: list[dict] = []
    problems: list[str] = []
    for case_dir in sorted(p for p in gate_dir.iterdir() if p.is_dir()):
        spec = case_dir / "case.json"
        if not spec.is_file():
            problems.append(f"{case_dir.name}: no case.json")
            continue
        try:
            data = json.loads(spec.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"{case_dir.name}: unreadable case.json ({type(exc).__name__})")
            continue
        missing = [k for k in _REQUIRED_KEYS if k not in data]
        if missing:
            problems.append(f"{case_dir.name}: case.json missing {', '.join(missing)}")
            continue
        if not str(data["incident"]).strip():
            problems.append(f"{case_dir.name}: empty incident is not a reason")
            continue
        data["_dir"] = case_dir
        cases.append(data)
    return cases, problems


def run_case(scripts: Path, gate: str, case: dict) -> tuple[int, str]:
    """Return (exit code, combined output).

    The output is RETURNED rather than discarded because an exit code alone does
    not discriminate. `check_plan_totals` has four distinct exit-2 branches; two
    fixtures assert 2, and until `stdout_contains` existed either could have
    started returning 2 from a different branch and still passed -- two copies of
    one test wearing different names. This PR fixed exactly that defect in its own
    unit tests, by adding message assertions after a landed mutation left all
    twelve green, and did not carry the fix to the fixture schema until the
    adversarial review pointed at it.

    A `timeout` is passed because `test_gate_crash_exit_code._run` passes one and
    this call site did not; a fixtured gate that hangs would otherwise hang the CI
    job with no diagnostic.
    """
    argv = [str(scripts / gate)] + [a.replace("{dir}", str(case["_dir"])) for a in case["argv"]]
    proc = subprocess.run(  # noqa: S603
        [sys.executable] + argv,
        capture_output=True,
        text=True,
        # BOTH ends pinned, and one alone is worse than neither.
        #
        # `text=True` alone decodes with the ANSI codepage on Windows, so a
        # gate printing an em dash, a section sign or a curly quote comes back
        # mojibake and silently stops matching its fixture.
        #
        # Adding `encoding="utf-8"` alone is WORSE: the child still WRITES
        # cp1252, so decoding raises UnicodeDecodeError inside subprocess's
        # reader THREAD, which swallows it and hands back an EMPTY string with
        # a normal return code. Measured on
        # `check_audit_evidence/2026-08-empty-changed-file-list`: 96 chars and
        # the expected phrase became 0 chars and a failed contract, with no
        # error surfacing to this caller. A decode failure that reads as "the
        # gate printed nothing" is the silent-success shape in the harness
        # built to find it.
        #
        # `PYTHONIOENCODING` makes the child EMIT utf-8, so the two ends agree
        # by construction rather than by the platform defaults happening to
        # match -- derivation over synchronization.
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        encoding="utf-8",
        timeout=120,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _contract_failures(gate: str, cases: list[dict]) -> list[str]:
    out: list[str] = []
    if not [c for c in cases if int(c["expect"]) == 0]:
        out.append(f"{gate}: no case that the gate passes")
    if not [c for c in cases if int(c["expect"]) == 1]:
        out.append(
            f"{gate}: NO NEGATIVE CONTROL -- no case expects exit 1, so these "
            f"fixtures prove the gate runs, not that it discriminates"
        )
    # Exit 1 and exit 2 are the two codes D-051 exists to keep apart, so the
    # negative control must be a 1 specifically. `!= 0` admitted a 2, which would
    # have let a gate be "covered" by fixtures proving only that it can refuse to
    # look -- the two branches merged, inside the gate whose organising principle
    # is that they never share one. Latent when found: all four covered gates
    # already had a 1.
    for case in [c for c in cases if int(c["expect"]) == 2 and not c.get("stdout_contains")]:
        out.append(
            f"{gate}/{case['_dir'].name}: expects exit 2 without stdout_contains "
            f"-- a gate has several 'could not look' branches and the code alone "
            f"cannot say which one fired"
        )
    if not [c for c in cases if int(c["expect"]) == 2]:
        out.append(
            f"{gate}: no case expects exit 2 -- the fail-closed half of this "
            f"gate ('I could not look') is unfixtured"
        )
    if not [c for c in cases if c.get("adversarial")]:
        out.append(
            f"{gate}: no case marked adversarial -- ordinary cases test the "
            f"rule, adversarial cases test the boundary. It is the only one of "
            f"the four that looks for inputs the author did not already have "
            f"in mind: the other three are answerable from the code you just "
            f"wrote, this one only by asking what someone else would "
            f"reasonably send"
        )
    return out


def main(argv: list[str]) -> int:
    default_root = Path(__file__).resolve().parents[1] / "tests" / "gates"
    explicit_root = len(argv) > 1
    root = Path(argv[1]).resolve() if explicit_root else default_root
    if not root.is_dir():
        print(f"check-gate-fixtures: fixture root not found: {root}")
        return 2
    scripts = scripts_dir_for(root)
    if not scripts.is_dir():
        print(f"check-gate-fixtures: no scripts directory beside {root}")
        return 2

    gates = discover_gates(scripts)
    if not gates:
        print(f"check-gate-fixtures: no check_*.py discovered under {scripts}")
        return 2

    # #318. Shell gates and the wiring check read the REPO around the fixture
    # root, so whether they run is decided by whether that repo can be found --
    # not by which mode this was invoked in.
    #
    # It keyed on `explicit_root` for one round, which was a blanket exemption
    # wearing a derivation's clothes: every unit test that drives `main` passes
    # an explicit root, so the wiring verdict -- this change's whole point --
    # was reachable from no test at all. It also said nothing useful about the
    # api container, which passes no explicit root and still cannot see
    # `.github/`.
    #
    # Now a test that builds a repo-shaped tmp tree reaches the real branch,
    # and one that does not gets a PRINTED skip. "I did not look" must never be
    # indistinguishable from "I looked and it was fine" -- this file's
    # organising rule, applied to itself, which it was not.
    shell_gates: list[str] = []
    repo_checked = False
    repo = repo_root_for(root)
    if repo is None:
        # NOT a crash and NOT a pass. The repo root is genuinely out of
        # reach inside the api container, which mounts `apps/api` at
        # `/app` (#314) -- there is no `.github/` to find. The fixture
        # half below still runs and still means something; the repo-derived
        # half cannot, and says so.
        print(
            "check-gate-fixtures: NOT CHECKED -- no `.github/workflows` above "
            f"{root}, so shell-gate discovery and the gate-wiring check have "
            "nothing to read. Expected inside the api container (#314); on a "
            "full checkout it means the repo root moved."
        )
    else:
        shell_dir = shell_gates_dir_for(repo)
        if not shell_dir.is_dir():
            print(f"check-gate-fixtures: no shell-gate directory at {shell_dir}")
            return 2
        shell_gates = discover_shell_gates(shell_dir)

        # No `is_dir()` guard here, and its absence is deliberate:
        # `repo_root_for` RETURNS a directory only when `.github/workflows` is
        # one, so a guard here would test the predicate that selected `repo`.
        # A first draft carried it, which read as a fail-closed branch and was
        # unreachable by construction -- a dead guard invites the next reader
        # to believe it fires. The reachable "I could not look" for this half
        # is `repo is None`, above, which is printed rather than returned
        # because the fixture checks below are still worth running.
        workflows = workflows_dir_for(repo)
        # An EMPTY workflows directory is "I could not look", not "every gate
        # is unwired". Without this, `text` is empty, every stem is absent from
        # it, and the run prints the violation message and returns 1 -- the
        # code reserved for "I looked and something is wrong", in the file
        # whose organising principle is that those two never share one. Loud
        # either way, and mislabelled, which is the harder thing to debug.
        if not any(workflows.glob("*.y*ml")):
            print(
                f"check-gate-fixtures: no workflow files under {workflows} -- "
                "cannot tell a wired gate from an unwired one"
            )
            return 2

        # Every gate, both languages. A gate no workflow runs cannot fail,
        # and until #318 nothing in this repo said so -- two shell gates
        # shipped with real assertions inside and nothing invoking either.
        repo_checked = True

        # THE THIRD ORACLE (#296, #327). The two Python registries -- the
        # marker `discover_gates` reads and the hand list in
        # `test_gate_crash_exit_code.GATES` -- are cross-checked against EACH
        # OTHER, so a script missing from both is invisible to that check. It
        # passed BECAUSE what it should have found was not in the registry.
        # This arm derives its population from the WORKFLOWS instead, which is
        # a different file written by a different hand, so it can see what
        # neither registry lists.
        undiscovered = undiscovered_gates(scripts, workflows, compose_sources(repo))
        if undiscovered:
            print(
                "check-gate-fixtures: FAILED -- scripts CI runs that are "
                "neither gates nor declared non-gates:"
            )
            for name in undiscovered:
                print(
                    f"  {name}: a workflow invokes it, it carries no "
                    f"crash-is-not-a-verdict handler, and it is not in "
                    f"NON_GATE_SCRIPTS. Either it is a gate missing the marker "
                    f"-- in which case no registry can see it and its green "
                    f"means nothing -- or it is not a gate and belongs in "
                    f"NON_GATE_SCRIPTS with a reason."
                )
            return 1

        unwired = unwired_gates(sorted(gates) + shell_gates, workflows, compose_sources(repo))
        if unwired:
            print("check-gate-fixtures: FAILED -- gates no workflow invokes:")
            for name in unwired:
                print(
                    f"  {name}: nothing under .github/workflows runs it, so it "
                    f"cannot fail and its green means nothing"
                )
            return 1

    # Shell gates carry their own both-states evidence rather than fixtures, so
    # they are covered by DEFERRED. The requirement that survives is that they
    # cannot appear in SILENCE: a new one with no entry here fails the run.
    unknown_shell = [g for g in shell_gates if g not in DEFERRED]
    if unknown_shell:
        print("check-gate-fixtures: FAILED -- shell gates with no stated coverage:")
        for name in unknown_shell:
            print(
                f"  {name}: not in DEFERRED. A shell gate cannot be fixtured by "
                f"this harness, so it must say here how it is evidenced."
            )
        return 1

    # Shell entries are excluded whenever the repo half did not RUN -- an
    # explicit fixture root, or a tree with no `.github/workflows` above it --
    # rather than reported missing. Both skips are printed, and turning a
    # declared skip into a violation would make the harness unusable against
    # its own tmp_path fixtures and inside the api container.
    #
    # Keyed on `repo_checked` rather than on `explicit_root`, because those
    # stopped being the same question the moment the container case existed:
    # the container has no explicit root and still cannot see the shell gates.
    known = set(gates) | set(shell_gates)
    unknown = sorted(
        name
        for name in set(DEFERRED) - known
        if not (not repo_checked and name.endswith(_SHELL_GATE_SUFFIX))
    )
    if unknown:
        print("check-gate-fixtures: DEFERRED names gates that do not exist:")
        for name in unknown:
            print(f"  {name}")
        return 2

    failures: list[str] = []
    unreadable: list[str] = []
    gaps: list[str] = []
    checked = 0

    for gate in gates:
        gate_dir = root / gate.removesuffix(".py")
        if not gate_dir.is_dir():
            if gate not in DEFERRED:
                failures.append(f"{gate}: no fixtures and not in DEFERRED")
            continue
        if gate in DEFERRED:
            failures.append(f"{gate}: has fixtures AND is in DEFERRED -- pick one")
            continue

        cases, problems = load_cases(gate_dir)
        unreadable += [f"{gate}/{p}" for p in problems]
        if problems:
            continue
        if not cases:
            unreadable.append(f"{gate}: fixture directory contains no cases")
            continue

        failures += _contract_failures(gate, cases)

        for case in cases:
            checked += 1
            want = int(case["expect"])
            got, output = run_case(scripts, gate, case)
            name = case["_dir"].name
            if got != want:
                failures.append(
                    f"{gate}/{name}: expected exit {want}, got {got} "
                    f"[incident: {case['incident']}]"
                )
            needle = case.get("stdout_contains")
            if needle and needle not in output:
                failures.append(
                    f"{gate}/{name}: exit {got} was correct but the output does "
                    f"not contain {needle!r} -- the case may be passing from a "
                    f"different branch than it names"
                )
            gap = case.get("gap")
            if gap:
                gaps.append(
                    f"{gate}/{name}: returns {want}, should return "
                    f"{gap.get('should_be')} -- {gap.get('issue')}"
                )

    for line in gaps:
        print(f"check-gate-fixtures: KNOWN GAP {line}")

    if unreadable:
        print("check-gate-fixtures: could not read fixtures (exit 2, NOT a pass):")
        for line in unreadable:
            print(f"  {line}")
        return 2
    if failures:
        print("check-gate-fixtures: FAILED")
        for line in failures:
            print(f"  {line}")
        return 1

    # Counted from the gates the loop actually VISITED, not `len(gates) -
    # len(DEFERRED)`. That expression was correct while `DEFERRED` held only
    # Python names; putting shell gates in it made the subtraction cross two
    # populations, and the line printed 5 where 7 had been exercised. A success
    # message that understates its own coverage is the mildest version of this
    # file's subject, and nothing asserts the string, so nothing caught it.
    covered = len([g for g in gates if g not in DEFERRED])
    print(
        f"check-gate-fixtures: {checked} cases across {covered} gates behaved as "
        f"specified ({len(DEFERRED)} deferred with reasons)"
    )
    return 0


if __name__ == "__main__":
    # A crash must not share an exit code with "found something": Python exits 1
    # on an unhandled exception, which is this gate's violation code.
    try:
        raise SystemExit(main(sys.argv))
    except (SystemExit, KeyboardInterrupt):
        # KeyboardInterrupt re-raised, NOT relabelled 2. Every other gate does
        # this, and `test_gate_crash_exit_code` forbids the alternative for all
        # of them: reporting Ctrl-C as "I could not look" is a verdict the user
        # never asked for. This file deviated until the adversarial review of
        # PR #216 read the nine and then read this one.
        raise
    except BaseException as exc:  # noqa: BLE001 - deliberate: crash != verdict
        # stderr, not stdout: the success line goes to stdout, and a crash notice
        # sharing that stream is one grep away from being read as output.
        print(
            f"check-gate-fixtures: CRASHED: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(2) from exc
