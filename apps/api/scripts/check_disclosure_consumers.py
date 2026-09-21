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
is load-bearing rather than tidy. `zt.py::GapAnalysisResponse.unusable_target_codes`
has no reference anywhere under `apps/web/src` and is rendered by
`zt/exporters.py` into the client's deliverable -- so a web-only search reports
a defect over a field that already reaches the reader who matters most.

That was nearly shipped. The issue's own sketch said "referenced anywhere under
`apps/web/src`", which was the right shape for #316's `excluded_inputs` and the
wrong one here. A known-good shape carries no marker saying what made it right;
what made it right there was that the reader was a consultant at a screen.

**And the widening then paid for itself in the other direction.** The SIBLING
field `clients.py::ZtDashboardResponse.unusable_target_codes` -- same name,
different model, same service -- reaches no screen either, and the deliverable
evidence above is not its evidence: it exists precisely so the client's screen
does not disagree with the client's PDF. Crediting the PDF for it cleared the
one field whose whole reason is that the PDF is not enough. Which is why a
reader is attributed by the MODEL'S SUBJECT rather than by a service token --
see `unconsumed` -- and why #387 is filed rather than quietly passing.

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

#: Fields this gate does not currently require a reader for, each with its
#: reason and -- for every entry standing today -- an issue that deletes it.
#:
#: The `DEFERRED` shape from `check_gate_fixtures.py`, and for the same reason:
#: "no consumer" and "deliberately no consumer" must be different states, or
#: the gate's first red is cleared by deleting the check.
#:
#: NOT EMPTY ON LANDING, and the header used to say it was. That sentence
#: ("EMPTY ON LANDING ... every disclosure field on this tree already reaches a
#: screen or a deliverable") stood directly above two entries contradicting it,
#: and the entries were the honest half: a reader who believed the header would
#: conclude the tree is clean and never scroll four lines. Every entry below is
#: a REAL unconsumed disclosure, exempt only so the gate can land detecting the
#: rest -- which is the opposite claim from "genuinely API-only", and the
#: distinction is what tells the next person whether there is work here.
#:
#: Keyed on `"<origin>::<Model>.<field>"` -- the SAME string a violation is
#: reported as -- and NOT on the bare field name. `source_rows_total` exists on
#: three models, `unusable_target_codes` on two, `batches_total` on two, so a
#: name-keyed exemption written for one would silently cover every twin. That
#: is the unstated-exemption shape, and keying it on the triple removes the
#: possibility rather than documenting it.
#:
#: An entry here EXPIRES: `expired_field_exemptions` below turns the gate red
#: when the field acquires a reader, or when the model or field it names is
#: gone. Without that, the first person to render one of these gets no signal,
#: the entry stays forever, and a future twin inherits an exemption written for
#: a defect somebody already fixed.
EXEMPT_FIELDS: dict[str, str] = {
    "clients.py::ZtDashboardResponse.unusable_target_codes": (
        "TEMPORARY, tracked in #387. The field this gate shipped BLIND to, and "
        "the reason the attribution below is keyed on the model's subject "
        "rather than on a path token. Nothing under `apps/web/src` mentions it; "
        "the evidence that cleared it was `app/zt/exporters.py` reading the "
        "identically-named field of the OTHER ZT model. Its own comment says it "
        "exists so the client's screen does not disagree with the client's PDF, "
        "so clearing it with the PDF is the one reading that cannot be right. "
        "DELETE THIS when the ZT dashboard renders the codes."
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


def model_subject(model: str) -> str:
    """The model name with its `Response` suffix removed.

    `ZtDashboardResponse` -> `ZtDashboard`; `GapAnalysisResponse` ->
    `GapAnalysis`. One transformation, derived from the model itself, with no
    vocabulary of role nouns to keep in sync.
    """
    return model[: -len("Response")] if model.endswith("Response") else model


def readers_for(field: str, subject: str, readers: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Readers that mention the field AND name the model's subject, same file.

    Both conditions in ONE file is the whole of the attribution. A file that
    names the subject is handling that model; a field name inside it is that
    model's field.
    """
    pattern = re.compile(rf"(?<!\w){re.escape(field)}(?!\w)")
    return [(p, b) for p, b in readers if pattern.search(b) and subject in b]


def unconsumed(
    fields: list[tuple[str, str, str]], readers: list[tuple[str, str]]
) -> list[tuple[str, str, str]]:
    """Fields whose name appears in no reader THAT NAMES THEIR OWN MODEL.

    ## Two false-pass mechanisms, and the second survived the fix for the first

    A pooled blob match asks "does this name appear anywhere a person reads".
    Field names are NOT unique across models -- `batches_total` is declared on
    both `AttackRunAiResponse` and `RiskRegisterResponse` -- so the Risk fields
    matched ATT&CK's renderer and passed. **The gate ran green over a live
    instance of the defect it exists to catch.**

    Scoping the match to the field's SERVICE, by path token, fixed that pair
    and left the shape alive one level down: two models of the SAME service
    still share every token. `clients.py::ZtDashboardResponse` and
    `zt.py::GapAnalysisResponse` both declare `unusable_target_codes`, both
    carry the token `zt`, and `app/zt/exporters.py` reads the second one -- so
    the first passed on the second's evidence, reaching no screen at all
    (#387). The file-stem token widened it further: every model in
    `clients.py` carried `clients`, a token shared by five services.

    ## What replaced it: the reader must name the MODEL'S SUBJECT

    A reader counts for `<Model>.<field>` only when ONE file contains both the
    field name (word-bounded) and `model_subject(Model)` as a substring. The
    signal is content rather than path, and it exists because this repo's
    readers name what they read: `lib/risk/types.ts` declares `RiskRegister`,
    `lib/dashboards/techDebt.ts` declares `TechDebtDashboardData`,
    `lib/attack/types.ts` declares `AttackRunAiResponse`, and
    `app/zt/exporters.py` imports `GapAnalysis`. Only one reader has to carry
    both, so a component that destructures fields without naming the type is
    covered by the types file it imports from.

    MEASURED on this tree, all eighteen fields: fifteen attributed to a reader
    that names their own model, and three flagged -- the Risk `batches_*` pair
    (#372) and the ZT dashboard field (#387). Every one of the fifteen is a
    true positive read by hand, including both cross-file cases
    (`clients.py` models under `components/dashboards/techDebt/`,
    `GapAnalysisResponse` in `app/zt/exporters.py`) and both remaining
    duplicate names, which now resolve to different files.

    It fails CLOSED in the direction that matters: a reader this cannot
    attribute produces a violation someone must answer, never a pass.

    ## What it still over-matches, stated because the direction is the quiet one

    Within one model's files this is still a bare word-boundary match: a field
    named after a common word is satisfied by any prose in the file that names
    the model. The alternative is parsing TSX for property access, which is a
    second implementation of a TypeScript compiler and is how a gate stops
    being maintained.

    The subject match is a plain SUBSTRING, and it must be -- the readers say
    `TechDebtDashboardData` and `AttackRunAiResponse`, so a word boundary would
    reject every real one. The cost is that a subject CONTAINED IN another
    subject would let that model's reader clear it, which is this same
    cross-model false pass one level up. LATENT rather than live: measured on
    this tree, no subject is a substring of another (`AttackRunAi`,
    `CapabilityList`, `GapAnalysis`, `RiskEntry`, `RiskRegister`,
    `TechDebtDashboard`, `ZtDashboard`).
    `test_no_model_subject_is_a_substring_of_another` re-derives that from the
    real schemas, so it goes red when a model lands that breaks it instead of
    being a sentence that was true once.
    """
    out = []
    for origin, model, field in fields:
        if f"{origin}::{model}.{field}" in EXEMPT_FIELDS:
            continue
        if not readers_for(field, model_subject(model), readers):
            out.append((origin, model, field))
    return out


def expired_field_exemptions(
    fields: list[tuple[str, str, str]],
    readers: list[tuple[str, str]],
    origins: set[str],
) -> list[tuple[str, str]]:
    """Entries in `EXEMPT_FIELDS` that have stopped standing for anything.

    Two ways an exemption expires, and both must be LOUD:

      * the field now HAS a reader. Somebody did the work. Without this check
        they get no signal, the entry survives, and the gate is permanently
        blind to a field it could now be enforcing -- which is the state
        `AUDIT_RENDERER_EXEMPT` was written to avoid and could not detect.
      * the field is GONE from a schema file that IS present -- the model was
        renamed or the field deleted. The entry then exempts nothing, and the
        next field to land under that triple inherits a reason written about a
        different defect.

    `check_gate_fixtures.py`'s `DEFERRED` has both halves ("names gates that do
    not exist", "has fixtures AND is in DEFERRED -- pick one"). This file was
    modelled on that table and shipped with neither.

    ## `origins` is the scope, and leaving it out made the check WRONG

    The first version judged every key against whatever tree `main` was pointed
    at. `main` is pointed at a fixture tree by every test in this gate's suite,
    and a fixture tree has no `risk.py` -- so all three real exemptions were
    reported stale, in eight tests at once, and the "expired" verdict was
    really "you are looking at a different repository". Caught by running it,
    which is the only thing that catches it: the code reads correctly and the
    message it prints is a confident, specific lie.

    So an exemption is judged only where its ORIGIN FILE is present. The
    residual is deliberate and covered elsewhere rather than silently: an
    exemption naming a schema file that has been DELETED outright is invisible
    here, because from inside this function that is indistinguishable from a
    fixture. `test_every_exemption_names_a_field_that_EXISTS` asserts it
    against the real tree, where the question is answerable.
    """
    declared = {f"{origin}::{model}.{field}" for origin, model, field in fields}
    by_key = {f"{origin}::{model}.{field}": (model, field) for origin, model, field in fields}
    expired: list[tuple[str, str]] = []
    for key in EXEMPT_FIELDS:
        origin = key.split("::", 1)[0]
        if origin not in origins:
            continue
        if key not in declared:
            expired.append(
                (
                    key,
                    f"{origin} is present and declares no such disclosure field "
                    f"-- the model or the field was renamed, so the exemption is stale",
                )
            )
            continue
        model, field = by_key[key]
        hits = readers_for(field, model_subject(model), readers)
        if hits:
            where = ", ".join(sorted(p for p, _ in hits)[:3])
            expired.append((key, f"now read by {where} -- delete the exemption"))
    return expired


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
                f"dropped, and no screen or exporter that names "
                f"`{model_subject(model)}` reads it. The endpoint is not the "
                f"surface."
            )
            print(
                "      (The name may well appear elsewhere, including in this "
                "service's own files. A field declared on two models is read "
                "for one and not the other, which is exactly what a pooled -- "
                "or a per-service -- search cannot see.)"
            )
        print(
            "  Either render it, or add it to EXEMPT_FIELDS with the reason it "
            "is genuinely API-only. 'No consumer' and 'deliberately no "
            "consumer' must not be the same state."
        )

    expired = expired_field_exemptions(fields, readers, {p.name for p in schemas.glob("*.py")})
    if expired:
        failed = True
        print("check-disclosure-consumers: FAILED -- EXPIRED exemptions in EXEMPT_FIELDS:")
        for key, why in expired:
            print(f"  {key} -- {why}")
        print(
            "  An exemption that has stopped standing for anything is worse "
            "than none: it reads as a decision somebody made about a state "
            "that no longer exists, and it silently covers the next field to "
            "arrive under the same key."
        )

    has_generic_reader = audit_payload_has_a_generic_reader(repo)
    if not has_generic_reader:
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
    elif AUDIT_RENDERER_EXEMPT is not None:
        # THE EXPIRY. Without it, `AUDIT_RENDERER_EXEMPT` is read exactly once
        # -- on the runs where arm 2 fails -- and is never read again after
        # #351 lands. The exemption would then sit in this file forever, and
        # arm 2 would be held open by a string describing a defect somebody
        # already fixed: the gate could not go red if the renderer were later
        # deleted, because the exemption would catch it.
        #
        # A DEFERRAL THAT CANNOT DETECT ITS OWN DISCHARGE IS A PERMANENT
        # EXEMPTION WEARING AN EXPIRY DATE. `check_gate_fixtures`'s `DEFERRED`
        # -- the table this one was modelled on -- refuses an entry that has
        # fixtures ("pick one"); this is that check, for this exemption.
        failed = True
        print(
            "check-disclosure-consumers: FAILED -- EXPIRED exemption: "
            "`AUDIT_RENDERER_EXEMPT` is set, and a generic `details` renderer "
            "now exists."
        )
        print(
            "  The exemption's own text says it is deleted when #351 merges. "
            "It has. Set `AUDIT_RENDERER_EXEMPT = None` -- arm 2 then passes "
            "for real rather than by exemption, and goes red if the renderer "
            "is ever removed, which it cannot do while this string is set."
        )

    if failed:
        return EXIT_VIOLATION

    # The count and the caveat in one sentence, because "all reachable ... (3
    # exempt with reasons)" is the EXEMPT_FIELDS header's own defect in the
    # line a reader actually sees: it states a clean verdict and then names, in
    # a parenthesis, the fields it is not a verdict about. Every exemption here
    # is a REAL unconsumed disclosure, so the clean line has to say so.
    # Exemptions that apply to the tree ACTUALLY inspected, not `len(EXEMPT_FIELDS)`.
    # The global count produced "-2 of 1 disclosure fields" on a fixture tree,
    # which is the arithmetic saying out loud that it is describing a different
    # repository -- the same scope error `expired_field_exemptions` had, in the
    # summary line rather than the verdict. Found by reading the output of a
    # red-on-revert run, not by a test: every test here asserts an exit code,
    # and a nonsense count does not change one.
    applied = sorted(k for k in EXEMPT_FIELDS if k in {f"{o}::{m}.{f}" for o, m, f in fields})
    print(
        f"check-disclosure-consumers: {len(fields) - len(applied)} of "
        f"{len(fields)} disclosure fields reach a screen or a deliverable"
        + (
            f"; {len(applied)} do NOT and are exempt with a tracked reason -- "
            f"{', '.join(applied)}"
            if applied
            else ""
        )
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
