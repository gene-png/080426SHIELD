#!/usr/bin/env python3
"""Compute the merge rule's gated conditions from the diff, and refuse a PR body
that understates them.

`CLAUDE.md`'s merge rule says an agent merges unattended only when six
conditions hold, and that "any PR tripping 4, 5 or 6 comes back to the human".
Conditions 4 and 5 are path questions with exact answers, and until now both
were answered from memory by whoever wanted to merge -- the rule itself calls
condition 5 "mostly a path match", which is an invitation to get the match wrong
in the direction that suits you.

## What this gate enforces, and what it deliberately does not

It computes conditions 4 and 5 from the changed-file list and compares that
against what the PR body CLAIMS. A body naming every computed condition passes.
A body omitting one FAILS, printing the paths that trip it.

It does NOT refuse a PR for tripping a condition. That was the first design and
it is wrong: condition 5 is tripped by most code PRs here -- 13 of the last 15
merges, by the rule's own measurement -- so a gate that reddened on it would be
red on nearly every PR, and `CLAUDE.md` records what a routinely-and-correctly
ignored rule teaches: that the rules are advisory, which is expensive for the
ones that are not. A permanently red required check trains people to merge past
red.

So the enforced property is HONESTY ABOUT THE PATHS, not abstention. The failure
this closes is a body reading "trips nothing" over a diff that trips three
things, which is the failure that actually happened and which re-reading the
path list does not prevent.

## Condition 6 is NOT computed, and saying so is the point

"Nothing that changes deliverable content, exporter output, or client dashboard
numbers" is a judgement about what a change MEANS. A path match cannot decide
it: a touched exporter might be a comment, and a `lib/dashboards/` edit can
alter a rendered number without touching any listed path. The merge rule already
calls 2, 3 and 6 self-attested. This makes 4 and 5 mechanical and leaves 6
exactly as honest as it was, rather than pretending a glob decided it.

## The gate set is DERIVED, not listed

`CLAUDE.md`: "derive the set; do not extend the list", with the membership test
"does any WORKFLOW execute it as a gate". `derived_gate_paths` runs that over
`.github/workflows/`, so a gate wired in a spelling this file has never heard of
still counts. The explicit table beside it covers what no workflow-grep can
find -- the scoring engines, the models, the prompts -- and every entry carries
why it is there.

## Silent-success branches, enumerated before the first line was written

Every path that could exit 0 without having looked:

  * an EMPTY changed-file list -> exit 2. An empty diff is not a clean diff; it
    is a checkout that did not fetch enough history, which is how
    `check_audit_evidence.py` once printed "documentation-only change, exempt"
    over input supporting neither reading.
  * a MISSING or unreadable changed-file or body file -> exit 2.
  * `derived_gate_paths` finding NOTHING -> exit 2. The workflows always execute
    gates; zero means the derivation broke, not that the repo has none.
  * no repo root above this file -> exit 2, rather than computing the derived
    half as empty and reporting on the explicit half alone.
  * no gated path touched -> exit 0, the one legitimate green, and it prints
    what it looked at so a reader can tell it from the others.

Exit codes follow D-051: 0 clean, 1 a real violation, 2 could not look.
"""

from __future__ import annotations

import re
import sys
from fnmatch import fnmatch
from pathlib import Path

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_COULD_NOT_LOOK = 2

#: Condition 4. A NEW revision under `alembic/versions/`.
#: `alembic/env.py` is NOT here -- it is condition 5, because changing it alters
#: stored behaviour without adding a revision, which is the distinction the
#: merge rule draws in as many words.
MIGRATION_GLOBS = ("apps/api/alembic/versions/*.py",)

#: Condition 5, the part no workflow-grep can find. Each entry is here because a
#: green suite proves least about it, and the reason is the merge rule's own.
EXPLICIT_CONDITION_5 = {
    "apps/api/app/ai/*": "the single egress path for all five services",
    "apps/api/app/ai/**": "the single egress path for all five services",
    "apps/api/app/csf/playbook.py": "deterministic scoring engine",
    "apps/api/app/risk/engine.py": "deterministic scoring engine",
    "apps/api/app/zt/scoring.py": "deterministic scoring engine",
    "apps/api/app/attack/coverage.py": "deterministic surface the first list missed",
    "apps/api/app/csf/scoring.py": "deterministic surface the first list missed",
    "apps/api/app/zt/maturity.py": "deterministic surface the first list missed",
    "apps/api/app/tech_debt/security_scope.py": "deterministic surface the first list missed",
    "apps/api/app/risk/exporters.py": "deterministic surface the first list missed",
    "apps/api/app/tech_debt/extract.py": "holds a live LLM prompt outside app/ai/",
    "apps/api/app/config.py": "decides whether the redactor may be disabled (#142)",
    "apps/api/app/models/*": "stored behaviour without a migration",
    "apps/api/app/models/**": "stored behaviour without a migration",
    "apps/api/alembic/env.py": "stored behaviour without a migration",
    "apps/api/tests/**": "weakening a test satisfies condition 1 more directly",
    "e2e/**": "weakening a test satisfies condition 1 more directly",
    "apps/web/**/*.test.ts": "the vitest suite condition 1 counts",
    "apps/web/**/*.test.tsx": "the vitest suite condition 1 counts",
    "apps/web/**/*.spec.ts": "the vitest suite condition 1 counts",
    "apps/web/**/*.spec.tsx": "the vitest suite condition 1 counts",
    "apps/api/scripts/seed_demo.py": "drives a CI job; clean seed data hid #130 for months",
    "scripts/demo-reset.sh": "drives a CI job",
    "docker-compose.yml": "defines the mounts every containerised gate reads",
    "docker-compose.demo.yml": "defines the mounts every containerised gate reads",
    ".github/workflows/**": "a change here satisfies condition 1 by construction",
    ".github/pull_request_template.md": "one colon decides whether a gate means anything",
    # THE GATES THEMSELVES, and these were MISSING from the first version of this
    # table because I assumed `derived_gate_paths` covered them. It does not, and
    # the distinction is worth stating: the derived set answers "is this EXECUTED
    # as a gate today", which a gate that has not been wired yet is not.
    #
    # Found by running this gate against its own PR. The diff was exactly
    # `apps/api/scripts/check_merge_rule_conditions.py`, and it reported
    # "clean -- none of 1 changed path(s) trips condition 4 or 5" over a new gate
    # script. `CLAUDE.md`'s condition 5 names `apps/api/scripts/check_*.py`
    # explicitly; dropping it on the belief that a derivation subsumed it is the
    # half-sweep this repo keeps recording, and self-application is what caught
    # it rather than any amount of re-reading.
    "apps/api/scripts/check_*.py": "a gate; a change here satisfies condition 1 by construction",
    "apps/api/scripts/leave_row_oracle.py": "a CI gate whose name does not match check_*",
    "tests/gates/**": "a CI gate written in shell (D-059a)",
}

#: Where a workflow's gate invocation can point. Loose on purpose: the whole
#: value is catching a spelling this file does not know. The published version
#: of this grep in `CLAUDE.md` once missed a dotted module and a second
#: workflow, and was credible because it had been run.
_GATE_INVOCATION = re.compile(
    r"(?:bash|python(?:3)?(?: -m)?)\s+([A-Za-z0-9_./-]*"
    r"(?:check_|leave_row_oracle|tests[/.]gates|scripts[/.])[A-Za-z0-9_./-]*)"
)


def repo_root_above(start: Path) -> Path | None:
    """The repo root, DERIVED by walking up for `.github/workflows`.

    Not `parents[N]`. That is a claim about where this file sits relative to a
    mount, and `apps/api` is mounted at `/app` for the lint gate while the whole
    tree is at `/work` for a full-checkout run -- the same expression names two
    directories. `check_disclosure_consumers.py::repo_root_for` argues the same.
    """
    for candidate in [start, *start.parents]:
        if (candidate / ".github" / "workflows").is_dir():
            return candidate
    return None


def _as_path(raw: str) -> str:
    """`scripts.check_test_integrity` -> `apps/api/scripts/check_test_integrity.py`.

    The dotted form appears in `python -m scripts.x` under
    `working-directory: apps/api`, so that directory is the module root. A diff
    never names the dotted form, so a set holding it would match nothing --
    silently, which is why this conversion exists rather than the raw string.
    """
    if "/" in raw or raw.endswith((".py", ".sh")):
        return raw
    if raw.startswith("scripts."):
        return "apps/api/" + raw.replace(".", "/") + ".py"
    return raw.replace(".", "/") + ".py"


def derived_gate_paths(repo: Path) -> tuple[set[str], list[str]]:
    """Every path a workflow executes as a gate. Returns (paths, problems)."""
    problems: list[str] = []
    workflows = repo / ".github" / "workflows"
    if not workflows.is_dir():
        return set(), [f"no .github/workflows under {repo}"]
    found: set[str] = set()
    for wf in sorted(workflows.glob("*.yml")) + sorted(workflows.glob("*.yaml")):
        try:
            text = wf.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            problems.append(f"{wf}: unreadable ({type(exc).__name__})")
            continue
        for raw in _GATE_INVOCATION.findall(text):
            found.add(_as_path(raw))
    return found, problems


def condition_4(changed: list[str]) -> list[str]:
    """Paths that make this PR a migration."""
    return sorted(p for p in changed if any(fnmatch(p, g) for g in MIGRATION_GLOBS))


def condition_5(changed: list[str], derived: set[str]) -> dict[str, str]:
    """Gated paths touched, mapped to WHY each is gated.

    The reason travels with the path so a failure can say what the human is
    being asked to look at, rather than only that a glob matched.
    """
    hits: dict[str, str] = {}
    for path in changed:
        for glob, why in EXPLICIT_CONDITION_5.items():
            if fnmatch(path, glob):
                hits[path] = why
                break
        else:
            if path in derived:
                hits[path] = "a workflow executes this as a gate"
    return dict(sorted(hits.items()))


def merge_rule_region(body: str) -> str:
    """The part of the body discussing the merge rule, or all of it.

    Scoped when a `Merge rule` heading exists, so a stray digit elsewhere -- a
    version, a count, an issue number -- cannot satisfy the check. Falls back to
    the WHOLE body rather than to nothing: a PR discussing the conditions
    without a heading is being honest in prose, and failing it would teach
    people to add a heading rather than to think about the paths.
    """
    match = re.search(r"(?im)^#+[ \t]*Merge[ \-]rule\b", body)
    if not match:
        return body
    rest = body[match.end() :]
    following = re.search(r"(?m)^#+[ \t]", rest)
    return rest[: following.start()] if following else rest


def acknowledges(body: str, condition: int) -> bool:
    """Whether the body names this condition number.

    Generous about phrasing and strict about the number: "condition 5",
    "conditions 4, 5 and 6" and "trips 5" all count. This is not a
    copy-editor -- the failure it exists to catch is the number being ABSENT,
    not being phrased unusually. The negative lookarounds stop `15` matching 5.
    """
    return re.search(rf"(?<!\d){condition}(?!\d)", merge_rule_region(body)) is not None


def _usage(stream) -> None:
    print(
        "  Usage: check_merge_rule_conditions.py --changed-files <file> --body <file>",
        file=stream,
    )


def main(argv: list[str]) -> int:
    changed_path: str | None = None
    body_path: str | None = None
    args = argv[1:]
    index = 0
    while index < len(args):
        if args[index] == "--changed-files" and index + 1 < len(args):
            changed_path = args[index + 1]
            index += 2
        elif args[index] == "--body" and index + 1 < len(args):
            body_path = args[index + 1]
            index += 2
        else:
            print(
                f"check-merge-rule-conditions: unknown argument {args[index]!r}.",
                file=sys.stderr,
            )
            _usage(sys.stderr)
            print(
                "  Refusing to report on input it could not parse -- an ignored\n"
                "  flag is how a gate reports clean having read nothing (#343).",
                file=sys.stderr,
            )
            return EXIT_COULD_NOT_LOOK

    if not changed_path or not body_path:
        print(
            "check-merge-rule-conditions: --changed-files and --body are both required.",
            file=sys.stderr,
        )
        _usage(sys.stderr)
        return EXIT_COULD_NOT_LOOK

    try:
        raw_changed = Path(changed_path).read_text(encoding="utf-8")
        body = Path(body_path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(
            f"check-merge-rule-conditions: could not read its input ({exc}).\n"
            "  Exit 2, not a pass. An unreadable diff is not a clean diff.",
            file=sys.stderr,
        )
        return EXIT_COULD_NOT_LOOK

    changed = [line.strip() for line in raw_changed.splitlines() if line.strip()]
    if not changed:
        print(
            "check-merge-rule-conditions: the changed-file list is EMPTY.\n"
            "  A PR changes something, so an empty list means the diff did not\n"
            "  resolve -- a shallow checkout, or the wrong base. Reading it as\n"
            "  'no gated paths' is the false green this gate exists to avoid;\n"
            "  see check_audit_evidence.py's is_code_change([]).",
            file=sys.stderr,
        )
        return EXIT_COULD_NOT_LOOK

    repo = repo_root_above(Path(__file__).resolve().parent)
    if repo is None:
        print(
            "check-merge-rule-conditions: no `.github/workflows` above this file,\n"
            "  so the DERIVED half of condition 5 cannot be computed. Exit 2\n"
            "  rather than reporting on the explicit half alone, which would be\n"
            "  a verdict over a smaller question than the one asked.",
            file=sys.stderr,
        )
        return EXIT_COULD_NOT_LOOK

    derived, problems = derived_gate_paths(repo)
    if problems:
        for problem in problems:
            print(f"check-merge-rule-conditions: {problem}", file=sys.stderr)
        return EXIT_COULD_NOT_LOOK
    if not derived:
        print(
            "check-merge-rule-conditions: the workflows execute ZERO gates.\n"
            "  That cannot be true of this repo, so the derivation broke rather\n"
            "  than the repo being gateless.",
            file=sys.stderr,
        )
        return EXIT_COULD_NOT_LOOK

    migrations = condition_4(changed)
    gated = condition_5(changed, derived)

    tripped: list[int] = []
    if migrations:
        tripped.append(4)
    if gated:
        tripped.append(5)

    if not tripped:
        print(
            f"check-merge-rule-conditions: clean -- none of {len(changed)} changed "
            f"path(s) trips condition 4 or 5. ({len(derived)} gate path(s) derived "
            f"from the workflows. Condition 6 is a judgement this gate does not "
            f"make -- see the module docstring.)"
        )
        return EXIT_OK

    for condition in tripped:
        label = "condition 4 (migration)" if condition == 4 else "condition 5 (gated paths)"
        print(f"check-merge-rule-conditions: this PR trips {label}:")
        if condition == 4:
            for path in migrations:
                print(f"    {path}  -- a new alembic revision")
        else:
            for path, why in gated.items():
                print(f"    {path}  -- {why}")

    missing = [c for c in tripped if not acknowledges(body, c)]
    if missing:
        names = ", ".join(str(c) for c in missing)
        print(
            f"\ncheck-merge-rule-conditions: FAILED -- the PR body does not name "
            f"condition(s) {names}.",
            file=sys.stderr,
        )
        print(
            "  The merge rule says a PR tripping 4, 5 or 6 comes back to the\n"
            "  human. THAT is not enforced here and is not meant to be; what is\n"
            "  enforced is that the PR says so. A body claiming fewer conditions\n"
            "  than the diff carries is the failure this exists to catch, and it\n"
            "  is the one that actually happened.\n"
            "  Add a `## Merge rule` section naming each condition listed above.",
            file=sys.stderr,
        )
        return EXIT_VIOLATION

    named = ", ".join(str(c) for c in tripped)
    print(
        f"\ncheck-merge-rule-conditions: clean -- the body names every condition "
        f"the diff trips ({named})."
    )
    return EXIT_OK


if __name__ == "__main__":
    # A crash must NOT share an exit code with "violations found". Python exits 1
    # on an unhandled exception, which is this gate's "found something" code, so
    # an uncaught error would read as a verdict it never reached.
    #
    # `BaseException` with both propagating cases NAMED, rather than the
    # equivalent `except Exception`: a handler that says out loud what it
    # declines to swallow does not rely on the reader knowing the inheritance
    # tree. `SystemExit` is somebody's deliberate exit code. `KeyboardInterrupt`
    # is an operator who knows exactly what happened and is owed 130, not
    # "could not look".
    #
    # THE FIRST VERSION OF THIS BLOCK OMITTED `KeyboardInterrupt` and swallowed
    # Ctrl-C into exit 2. `tests/unit/test_gate_crash_exit_code.py` caught it on
    # the first run -- that harness doing exactly its job on the newest gate in
    # the repo, and the reason the block is duplicated verbatim in every gate
    # rather than shared: an import is one more thing that can fail BEFORE the
    # handler is installed, which is the defect it exists to close.
    try:
        raise SystemExit(main(sys.argv))
    except (SystemExit, KeyboardInterrupt):
        raise
    except BaseException as exc:  # noqa: BLE001 - deliberate: crash != verdict
        nl = chr(10)
        sys.stderr.write(f"check-merge-rule-conditions: CRASHED: {type(exc).__name__}: {exc}{nl}")
        sys.stderr.write(f"A crash is not a clean report and not a violation (D-051).{nl}")
        raise SystemExit(EXIT_COULD_NOT_LOOK) from exc
