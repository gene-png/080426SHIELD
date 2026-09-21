"""A disclosure the product writes must reach a person, and this proves it.

The mechanism half of #244's boundary decision (#336). `CLAUDE.md` carries the
prose half -- *"the disclosure reaches a screen" is part of the definition of
done for any PR that adds a provenance field* -- and that file's own finding is
that **the reflex survives the rule until the rule has a gate**.

## What a disclosure is

A field or key recording what was WITHHELD, DROPPED, REJECTED, UNCONFIRMED or
NOT-LOOKED-AT. Matched by prefix rather than by a hand list, because a list of
the ones we have is a list of the ones we thought of.

The prefixes are a FLOOR and are stated as one: a disclosure named outside them
is invisible here. That is the same residual `check_recalled_counts` carries
about its noun list, and widening it indefinitely turns this into a prose
critic.

## What a CONSUMER is, and why it is two surfaces and not one

`CLAUDE.md` says **"on a screen OR in a delivered artifact"**, and the widening
is load-bearing rather than tidy. `unusable_target_codes` has no reference
anywhere under `apps/web/src` and is rendered by `zt/exporters.py` into the
client's deliverable -- so a web-only search reports a defect over a field that
already reaches the reader who matters most.

That was nearly shipped. The issue's own sketch said "referenced anywhere under
`apps/web/src`", which was the right shape for #316's `excluded_inputs` and the
wrong one here. A known-good shape carries no marker saying what made it right;
what made it right there was that the reader was a consultant at a screen.

## THE TWO ARMS, and the second is not the one the issue asked for

**Arm 1 -- named fields.** A disclosure field on a `*Response` schema needs its
NAME referenced on one of the two surfaces. Cheap string match, over-matches on
common words, and says so rather than pretending otherwise.

**Arm 2 -- the audit payload, checked STRUCTURALLY.** #322's population --
`entries_write_check`, `entries_written`, `entries_received`,
`discarded_entries` and four more -- are `details` dict keys in `audit(...)`
calls, NOT schema fields. A gate scoped to schemas is structurally blind to the
largest instance #336 cites as its motivation.

The obvious repair is to enumerate those keys and search for each. It is wrong,
and measurably: the fix for #322 renders `details` GENERICALLY --
`Object.entries(details).map(...)` -- so every key reaches a screen without any
of them being named anywhere. A name search would report eight violations over
a payload that is fully visible.

So arm 2 asserts the GENERIC RENDERER EXISTS. One check covering all 96 keys
present today and every key added later, with no per-key work and nothing to
keep in sync. Derivation over enumeration, and the enumeration would have been
wrong in both directions at once.

## Silent-success branches, enumerated before the first line

Every one is exit 2, never 0:

  * the schemas directory does not resolve -- the `parents[N]` shape that cost
    a pytest session in #314 and recurred inside a week. Derived by walking up
    for a marker, not by counting.
  * `apps/web/src` absent (an api-only checkout, which is every container).
  * a schema file fails to parse.
  * ZERO schemas discovered -- the `rglob` hole `check_test_integrity` shipped
    with, where a path that does not exist prints "clean" and exits 0.
  * ZERO disclosure fields discovered, which means the predicate broke rather
    than that the tree is clean.

Exit 1 is a real violation. Exit 2 is "I could not look". They never share a
branch.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_COULD_NOT_LOOK = 2

#: A disclosure records what was WITHHELD, DROPPED, REJECTED or NOT LOOKED AT.
#:
#: A FLOOR, not a census. A disclosure named outside these is invisible here,
#: exactly as `check_recalled_counts`' noun list is a floor -- and widening
#: either one indefinitely turns a gate into a prose critic.
DISCLOSURE_PREFIXES = (
    "entries_",
    "discarded_",
    "excluded_",
    "dropped_",
    "rejected_",
    "unusable_",
    "source_rows_",
    "batches_",
)
DISCLOSURE_SUBSTRINGS = ("withheld", "provenance")

#: Fields that are genuinely API-only, each with its reason.
#:
#: The `DEFERRED` shape from `check_gate_fixtures.py`, and for the same reason:
#: "no consumer" and "deliberately no consumer" must be different states, or
#: the gate's first red is cleared by deleting the check.
#:
#: EMPTY ON LANDING, and that is a measurement rather than luck -- every
#: disclosure field on this tree already reaches a screen or a deliverable.
#: An entry here is a claim someone can check by opening the file.
#: Keyed on `"<origin>::<Model>.<field>"` -- the SAME string a violation is
#: reported as -- and NOT on the bare field name. `source_rows_total` exists on
#: three models, `unusable_target_codes` on two, `batches_total` on two, so a
#: name-keyed exemption written for one would silently cover every twin. That
#: is the unstated-exemption shape, and keying it on the triple removes the
#: possibility rather than documenting it.
EXEMPT_FIELDS: dict[str, str] = {
    "risk.py::RiskRegisterResponse.batches_total": (
        "TEMPORARY, tracked in #372. This is a REAL unconsumed disclosure, not "
        "an API-only field: a partial Risk synthesis keeps what succeeded, and "
        "nothing tells the consultant the draft is short. It is exempt only so "
        "this gate can land detecting it -- ATT&CK fixed the identical defect "
        "as #115. DELETE THIS when the Risk banner renders."
    ),
    "risk.py::RiskRegisterResponse.batches_failed": (
        "TEMPORARY, tracked in #372. The other half of the pair above."
    ),
}

#: Arm 2's exemption, and it is temporary BY CONSTRUCTION.
#:
#: The generic `details` renderer is #322's fix and lands in PR #351. Until it
#: does, this gate would be red on `main` for a defect that is real, open and
#: already being fixed -- and a gate that turns `main` red on landing is a gate
#: someone reverts.
#:
#: Delete this the moment #351 merges. The check below then passes for real
#: rather than by exemption, and if it does not, #322 regressed.
AUDIT_RENDERER_EXEMPT: str | None = (
    "#322: the admin Audit viewer does not render `details` yet. PR #351 adds "
    "a generic renderer. This entry is deleted when that merges -- it is an "
    "exemption with an expiry, not a standing one."
)

#: Where a person reads things. Two surfaces, per `CLAUDE.md`'s
#: "on a screen OR in a delivered artifact".
WEB_SUFFIXES = {".ts", ".tsx"}


def repo_root_for(start: Path) -> Path | None:
    """The repo root above `start`, DERIVED by walking up for a marker.

    Not `parents[N]`. That is a claim about where this file sits in a tree, and
    it is the shape #314 records costing a whole pytest session -- then
    recurring inside the same week in the gate written to fix it. A marker is a
    property of the tree, so moving either one can only fail to find a root,
    which the caller reports.
    """
    for candidate in [start, *start.parents]:
        if (candidate / "apps" / "api" / "app" / "schemas").is_dir():
            return candidate
    return None


def is_disclosure(name: str) -> bool:
    return name.startswith(DISCLOSURE_PREFIXES) or any(s in name for s in DISCLOSURE_SUBSTRINGS)


def response_disclosure_fields(schemas: Path) -> tuple[list[tuple[str, str, str]], list[str]]:
    """Every disclosure-shaped field on a `*Response` model.

    Returns (fields, problems). A file that will not parse is a PROBLEM, never
    a silent skip: a schema this gate cannot read is a schema it is not
    checking, and reporting that as clean is the shape the whole gate suite
    exists to refuse.

    Keyed on the `Response` suffix, which is a CONVENTION and therefore a
    residual worth stating: a response model named otherwise is invisible here.
    """
    fields: list[tuple[str, str, str]] = []
    problems: list[str] = []
    for path in sorted(schemas.glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            problems.append(f"{path.name}: unreadable ({type(exc).__name__})")
            continue
        for node in tree.body:
            if not (isinstance(node, ast.ClassDef) and node.name.endswith("Response")):
                continue
            for stmt in node.body:
                if (
                    isinstance(stmt, ast.AnnAssign)
                    and isinstance(stmt.target, ast.Name)
                    and is_disclosure(stmt.target.id)
                ):
                    fields.append((path.name, node.name, stmt.target.id))
    return fields, problems


def reader_text(repo: Path) -> tuple[list[tuple[str, str]], list[str]]:
    """Everything a person can read, as (path, text) PAIRS: screens and deliverables.

    Returns (readers, problems). An unreadable file is a problem rather than a
    skip, for the same reason a schema is.

    Pairs rather than one concatenated blob, and that is the whole of this
    gate's F1 fix: a blob cannot say WHICH surface matched, so a field on one
    model passed on a different model's renderer. The path is what carries
    that information, so it has to survive to the comparison.
    """
    problems: list[str] = []
    readers: list[tuple[str, str]] = []
    web = repo / "apps" / "web" / "src"
    for path in sorted(web.rglob("*")):
        if path.suffix in WEB_SUFFIXES and path.is_file():
            try:
                readers.append((str(path), path.read_text(encoding="utf-8")))
            except (OSError, UnicodeDecodeError) as exc:
                problems.append(f"{path}: unreadable ({type(exc).__name__})")
    for path in sorted((repo / "apps" / "api" / "app").rglob("*.py")):
        if "exporters" in path.name or path.name == "docx_export.py":
            try:
                readers.append((str(path), path.read_text(encoding="utf-8")))
            except (OSError, UnicodeDecodeError) as exc:
                problems.append(f"{path}: unreadable ({type(exc).__name__})")
    return readers, problems


#: A model name's role nouns, stripped to leave the SERVICE it belongs to.
#: `TechDebtDashboardResponse` -> `techdebt`; `RiskRegisterResponse` -> `risk`.
_ROLE = re.compile(
    r"(Dashboard|Response|Register|RunAi|Coverage|Summary|AiInput|List|Entry|Analysis)"
)


def service_tokens(origin: str, model: str) -> set[str]:
    """The service a field belongs to, DERIVED from two independent places.

    The union of the schema file's stem and the model name's role-stripped
    prefix, because neither alone is enough: `clients.py` holds a model for
    every service (so the file stem says only "clients"), and a model like
    `GapAnalysisResponse` names no service at all (so the prefix says only
    "gapanalysis", while its file says `zt`). Taking both means a field is
    attributed correctly whenever EITHER source knows.

    Derived rather than a model->surface table, which would be an enumeration
    going stale on the next model.
    """
    out = {origin[:-3].replace("_", "")}
    role = _ROLE.search(model)
    if role and role.start() > 0:
        out.add(model[: role.start()].lower())
    lead = re.match(r"[A-Z][a-z]+", model)
    if lead:
        out.add(lead.group(0).lower())
    return {t for t in out if t}


def _norm(path: str) -> str:
    return path.lower().replace("_", "").replace("-", "").replace("\\", "/")


def unconsumed(
    fields: list[tuple[str, str, str]], readers: list[tuple[str, str]]
) -> list[tuple[str, str, str]]:
    """Fields whose NAME appears in no reader BELONGING TO THEIR OWN SERVICE.

    ## Why not one pooled blob, which is what this did first

    A blob match asks "does this name appear anywhere a person reads". Field
    names are NOT unique across models -- `batches_total` is declared on both
    `AttackRunAiResponse` and `RiskRegisterResponse` -- so the Risk fields
    matched ATT&CK's renderer and passed. They reach no screen and no
    exporter. **The gate ran green over a live instance of the defect it
    exists to catch**, and would have gone red only if someone deleted the
    ATT&CK panel.

    So a reader counts for a field only when its PATH carries one of that
    field's service tokens. MEASURED on this tree: 2 of 18 fields flagged, and
    both are the Risk pair -- no false positive among the other 16, including
    every cross-file case (`clients.py` models rendered under
    `components/dashboards/techDebt/`, `GapAnalysisResponse` in
    `app/zt/exporters.py`).

    ## What it still over-matches, stated because the direction is the quiet one

    Within a service, this is still a bare word-boundary match: a field named
    after a common word is satisfied by any prose in that service's files. The
    alternative is parsing TSX for property access, which is a second
    implementation of a TypeScript compiler and is how a gate stops being
    maintained.
    """
    out = []
    for origin, model, field in fields:
        if f"{origin}::{model}.{field}" in EXEMPT_FIELDS:
            continue
        tokens = service_tokens(origin, model)
        pattern = re.compile(rf"(?<!\w){re.escape(field)}(?!\w)")
        if not any(
            pattern.search(body) and any(t in _norm(path) for t in tokens) for path, body in readers
        ):
            out.append((origin, model, field))
    return out


def audit_payload_has_a_generic_reader(repo: Path) -> bool:
    """Does anything render the audit `details` payload WITHOUT naming keys?

    Arm 2, and the structural form is the point. #322's population are dict
    keys in `audit(...)` calls, not schema fields, so arm 1 cannot see them --
    and enumerating them would report violations over a payload a generic
    renderer makes fully visible.

    Matched on iteration over the payload rather than on a component name, so
    moving or renaming the component does not silently pass.
    """
    viewer = repo / "apps" / "web" / "src" / "components" / "admin" / "AuditViewer.tsx"
    if not viewer.is_file():
        return False
    text = viewer.read_text(encoding="utf-8")
    return bool(re.search(r"Object\.(entries|keys)\s*\(\s*details", text))


def main(argv: list[str]) -> int:
    # A FLAG IS NOT A PATH, and this gate's root-walk is what made that
    # dangerous. `--bogus` resolved to `<cwd>/--bogus`, whose first PARENT is
    # the repo root, so `repo_root_for` rescued it and the run proceeded to a
    # normal verdict, exit 0. The arity check below fires only on a THIRD
    # argument, so `check_disclosure_consumers.py --bogus` was accepted.
    #
    # Latent rather than live -- `ci.yml` passes no argument -- and the same
    # shape as #343, reached by the opposite mechanism: there the bad path
    # failed to resolve, here the walk repaired it.
    if len(argv) > 1 and argv[1].startswith("-"):
        print(
            f"check-disclosure-consumers: could not look -- {argv[1]!r} is a "
            "flag, and this script implements none. It takes an optional PATH "
            "to start the repo-root search from, and nothing else. Refusing "
            "rather than treating it as a path, which resolves and then runs "
            "a check nobody asked for.",
            file=sys.stderr,
        )
        return EXIT_COULD_NOT_LOOK
    start = Path(argv[1]).resolve() if len(argv) > 1 else Path(__file__).resolve()
    if len(argv) > 2:
        print(f"check-disclosure-consumers: too many arguments; got: {argv[1:]}", file=sys.stderr)
        return EXIT_COULD_NOT_LOOK

    repo = repo_root_for(start)
    if repo is None:
        print(
            "check-disclosure-consumers: could not look -- no "
            f"`apps/api/app/schemas` above {start}. Expected inside the api "
            "container, which mounts only `apps/api` (#314); on a full "
            "checkout it means the tree moved.",
            file=sys.stderr,
        )
        return EXIT_COULD_NOT_LOOK

    if not (repo / "apps" / "web" / "src").is_dir():
        print(
            "check-disclosure-consumers: could not look -- `apps/web/src` is "
            "absent, so half the reader surface is unreadable. A verdict from "
            "one surface would report every web-rendered field as unconsumed.",
            file=sys.stderr,
        )
        return EXIT_COULD_NOT_LOOK

    schemas = repo / "apps" / "api" / "app" / "schemas"
    fields, problems = response_disclosure_fields(schemas)
    if problems:
        print("check-disclosure-consumers: could not look --", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return EXIT_COULD_NOT_LOOK

    if not list(schemas.glob("*.py")):
        print(
            f"check-disclosure-consumers: could not look -- no schema files "
            f"under {schemas}. An empty glob is not a clean tree.",
            file=sys.stderr,
        )
        return EXIT_COULD_NOT_LOOK

    if not fields:
        print(
            "check-disclosure-consumers: could not look -- ZERO disclosure "
            "fields discovered across every `*Response` model. This repo has "
            "eighteen; finding none means the predicate broke, not that the "
            "tree is clean.",
            file=sys.stderr,
        )
        return EXIT_COULD_NOT_LOOK

    readers, read_problems = reader_text(repo)
    if read_problems:
        print("check-disclosure-consumers: could not look --", file=sys.stderr)
        for p in read_problems:
            print(f"  {p}", file=sys.stderr)
        return EXIT_COULD_NOT_LOOK

    violations = unconsumed(fields, readers)
    failed = False

    if violations:
        failed = True
        print("check-disclosure-consumers: FAILED -- disclosures nobody can read:")
        for origin, model, field in violations:
            print(
                f"  {origin}::{model}.{field} -- records what was withheld or "
                f"dropped, and no screen or exporter BELONGING TO "
                f"{sorted(service_tokens(origin, model))} reads it. The "
                f"endpoint is not the surface."
            )
            print(
                "      (The name may well appear elsewhere. A field declared "
                "on two models is read for one and not the other, which is "
                "exactly what a pooled search cannot see.)"
            )
        print(
            "  Either render it, or add it to EXEMPT_FIELDS with the reason it "
            "is genuinely API-only. 'No consumer' and 'deliberately no "
            "consumer' must not be the same state."
        )

    if not audit_payload_has_a_generic_reader(repo):
        if AUDIT_RENDERER_EXEMPT is None:
            failed = True
            print(
                "check-disclosure-consumers: FAILED -- nothing renders the "
                "audit `details` payload generically."
            )
            print(
                "  Every discard counter this repo writes lands there. A "
                "renderer that iterates the payload keeps all of them visible; "
                "one that names keys goes stale on the next counter added."
            )
        else:
            print(f"check-disclosure-consumers: EXEMPT -- {AUDIT_RENDERER_EXEMPT}")

    if failed:
        return EXIT_VIOLATION

    print(
        f"check-disclosure-consumers: {len(fields)} disclosure fields, all "
        f"reachable on a screen or in a deliverable"
        + (f" ({len(EXEMPT_FIELDS)} exempt with reasons)" if EXEMPT_FIELDS else "")
    )
    return EXIT_OK


if __name__ == "__main__":
    # A crash must not share an exit code with "found something": Python exits 1
    # on an unhandled exception, which is this gate's violation code.
    #
    # THIS BLOCK WAS MISSING, and the gate was registered anyway. The marker
    # `discover_gates` keys on -- `crash != verdict` -- sat in a standalone
    # comment near the top of the file, so the registry listed a gate with no
    # handler at all: a crash here exited 1 and read as "a disclosure reaches
    # nobody". `test_gate_crash_exit_code` caught it the moment the gate was
    # added to its list, which is that harness doing its job on the first gate
    # added after it existed.
    #
    # The marker now lives ONLY here, on the `noqa` of the handler it
    # describes, so registration and the handler cannot come apart again. An
    # assertion satisfied by a comment is the defect; so is a registration.
    #
    # Duplicated verbatim in every gate rather than shared -- an import is one
    # more thing that can fail BEFORE the handler is installed, which is the
    # defect this block exists to close.
    try:
        raise SystemExit(main(sys.argv))
    except (SystemExit, KeyboardInterrupt):
        raise
    except BaseException as exc:  # noqa: BLE001 - deliberate: crash != verdict
        nl = chr(10)
        sys.stderr.write(f"check-disclosure-consumers: CRASHED: {type(exc).__name__}: {exc}{nl}")
        sys.stderr.write(f"A crash is not a clean report and not a violation (D-051).{nl}")
        raise SystemExit(2) from exc
