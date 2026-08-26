#!/usr/bin/env python
"""Per-LEAVE-row oracle: which exemption rows in the redaction truth tables can
actually fail, and which pass for a reason unrelated to the branch they name?

WHY THIS EXISTS. A LEAVE row asserts `redact_for_ai(text) == text` -- "this
ordinary prose must survive the redactor untouched". Such a row is written to
pin a specific NARROWING GUARD: the boundary that stops `Fl` eating `Flowmon`,
the lookahead that stops the phone rule eating a dotted quad. But a LEAVE row
passes whenever nothing touches the text, and "the guard held" and "no rule was
ever interested in this string" produce identical green.

That is how 376 green cells certified a rule carrying nine live defects.

METHOD. Disable one guard at a time and record which LEAVE rows flip to failing.
A row that no single guard-removal can flip is not pinning any guard.

THE DIAGNOSIS THIS TOOL PRODUCED, 2026-08-25, and the reason it is kept:

    A table written FIRST is an independent specification.
    A table written AFTERWARDS is a transcript of what the rule does.

MEASURED, re-counted whenever the guard list or the corpus changes, and
CAREFUL about what the numbers support.

  THE PROVENANCE SPLIT -- 104 LEAVE rows, 22 guards, one run. Counting only
  rows in the risk class, tables written BEFORE their pattern (#130, PR #141)
  carried 2 of 53 unrelated, 3.8%; tables written alongside or after their rule
  (item 10) carried 16 of 38, 42.1%. An 11x split along provenance and not
  along subject matter, from ONE run of ONE tool over ONE corpus -- which is
  what makes it a comparison rather than a before/after. Both halves face the
  same hand-built guard list, so the list cannot manufacture the difference.
  This is the finding that supports the diagnosis above.

  THE AFTER NUMBER -- 145 LEAVE rows, 30 guards, 0 of 95 unrelated.

  WHAT IT DOES NOT SHOW, stated because an earlier draft of this docstring
  claimed it did. THREE things changed between the two runs: the item-10 tables
  were rewritten table-first, the guard list grew 22 -> 30, and the
  `defended-in-depth` class was added. The third moves rows out of `unrelated`
  BY DEFINITION, and limit #2 below says the second can only ever do the same.
  So "42.1% -> 0%" is not evidence that writing tables first caused the
  improvement; it is three changes and one number.

  Separating them would need the OLD tables re-run under the NEW guard list and
  classifier, and that experiment cannot be run cleanly: the old LEAVE rows were
  written against the old rules, so several no longer hold and the baseline is
  not green. Nothing here separates them, so nothing here should claim to.

  The honest statement is the narrow one: after the rewrite, no LEAVE row in the
  corpus fails to pin something. Whether the ordering caused that is supported
  by the provenance split above, which IS a controlled comparison, and not by
  the before/after, which is not.

These figures are recounted whenever the guard list changes -- an earlier draft
of this docstring quoted 21 guards and a 4.3x split, which went stale the moment
`contract/ignorecase` was added and the negative-control class was derived
rather than excluded by hand. Both edits were substantive and both left a
sentence two screens away silently wrong, which is this repo's standing
re-count trigger firing inside the tool that exists to measure counts.

FOUR OUTPUT CLASSES, and the last two both exist because the first draft
was wrong about them:

  load-bearing     Some single guard-removal makes this row fail. The row is
                   doing the job it was written for.
  unrelated        The row IS in the risk class -- removing every guard at once
                   does change it -- but no SINGLE guard removal does. Its
                   survival is not attributable to any one branch.
  negative-control Removing EVERY guard at once still leaves it unchanged, so no
                   guard could ever have been what saved it. `Splunk Enterprise`
                   contains no designator substring; the address rule was never
                   going to touch it. These rows are load-bearing against FUTURE
                   change -- if a rule edit ever puts them in the risk class,
                   they fire -- and asking "does removing a guard break this" is
                   simply the wrong question for them.

  defended-in-depth
                   No SINGLE guard-removal flips it, but some guard protects it
                   ALONE -- so two or more guards independently cover this row.
                   Reported separately because the first draft called these
                   "unrelated", which punished redundant protection: after the
                   B3/B9 fix, `Flat network segmentation is the core finding` is
                   covered by both the no-separator digit requirement and the
                   shared terminal guard, and removing either leaves the other.
                   The row had just become strictly safer and the measurement
                   called it worse. Detected with one run per guard (all guards
                   off EXCEPT one), not one per row.

  Both derived classes are DERIVED, not listed: negative-control is whatever
  survives the all-guards-off variant. A hand-written list of negative controls would be one more
  enumeration of what somebody thought of, and would read as special pleading
  around an inconvenient number.

TWO LIMITS ON EVERY NUMBER THIS PRINTS.

  1. The guard list is HAND-REGISTERED. A guard nobody modelled cannot kill a
     row, so a row may be pinning something real and still report `unrelated`.
  2. Therefore `unrelated` is an UPPER BOUND, and the direction of the error is
     known: modelling more guards can only move rows OUT of the unrelated set,
     never into it. A reported 30% may be a true 20%. It cannot be a true 40%.

  Neither limit is a reason to discount the split above -- both apply equally to
  every table, so they cannot manufacture an 11x difference between two halves
  of the same corpus.

RESIDUAL, stated so it is examined rather than assumed. `MUTATIONS` is a
hand-built list, which makes this tool an enumeration of what its author thought
of -- the exact failure it exists to detect, one level up. The way out is to
DERIVE mutations from the pattern's own structure: walk the compiled pattern's
alternations and named sub-patterns and widen each mechanically, so the guard
set comes from the regex rather than from recall. Not built, deliberately: the
hand list found an 11x signal on its first run and the derived version is a
larger piece of work. Recorded because a residual nobody wrote down gets
rediscovered at full price. Same firing condition as D-058's other residuals --
revisit when a guard is found that the list did not model.

WHAT IS GATED AND WHAT IS NOT. This script is a REQUIRED STEP, not a gate:
verifying rows needs judgement about what each row was for, and a tool that
scored rows pass/fail would be asserting more than it knows. Exactly one
property here can fail honestly on input nobody configured, and that one IS
gated -- `--check-registry` fails when a LEAVE table has no registered guards.
Without it, adding a table nobody wired up would report clean, which is "I could
not look" and "nothing to complain about" sharing an exit code: the shape this
repo has now produced three times in its own tooling, and this would have been
the fourth, inside the tool built to catch it.

EXIT CODES, per this repo's fail-closed convention (D-051):
  0 - ran, or (with --check-registry) every LEAVE table has guards registered
  1 - --check-registry: a LEAVE table has no registered guards
  2 - could not run: baseline not green, a mutation would not compile, or the
      source could not be restored (an unreadable input is NOT a pass)
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO_APP = Path(__file__).resolve().parents[1]
REDACT = REPO_APP / "app" / "ai" / "redact.py"
TESTS = REPO_APP / "tests" / "unit"

BS = chr(92)  # backslash, never typed literally -- see CLAUDE.md on heredocs


# Which guards each LEAVE table is written to exercise. Hand-registered, and
# `--check-registry` refuses a table that is missing from here. The VALUE is
# advisory (it says what the author believed); the KEY's presence is what is
# gated, because a table nobody thought about is the rot case.
TABLE_GUARDS: dict[str, list[str]] = {
    "SUFFIX_SHAPE_PROSE": [
        "addr/no-sep-branch-requires-digit",
        "addr/roman-branch-case-scoped",
        "addr/single-letter-refuses-when-number-follows",
    ],
    "POSITION_LEAVE": ["addr/pre-keyword-ordinal-required"],
    "PRODUCT_NAMES": ["addr/no-sep-branch-requires-digit", "addr/letter-prefix-capped-at-3"],
    "SECURITY_PROSE": ["addr/no-sep-branch-requires-digit"],
    "STREET_NEWLINE_LEAVE": ["addr/street-sep-crosses-newline"],
    "ADDRESS_SHAPES_LEAVE": [
        "addr/terminal-guard-shared",
        "addr/terminal-guard-case-scoped",
        "addr/citystatezip-determiner-guard",
        "addr/no-sep-branch-requires-digit",
        "addr/street-branch-case-scoped",
    ],
    "RESIDUAL_LEAKED": ["addr/no-sep-branch-requires-digit", "addr/letter-prefix-capped-at-3"],
    "PHONE_LEAVE": [
        "phone/no-letter-before-a-phone",
        "phone/leading-lookbehind",
        "phone/ipv4-guard",
        "phone/iso-date-guard",
        "phone/trailing-guard",
        "phone/digit-count-7-to-15",
        "phone/group-size-max-4",
        "phone/at-most-four-groups",
        "phone/shape-validator",
        "phone/maximal-match-start",
        "phone/maximal-match-end",
    ],
    "CAGE_LEAVE": ["cage/value-must-contain-a-digit", "cage/separator-is-hspace"],
    "CONTRACT_LEAVE": ["contract/ignorecase"],
    # Discovered by `discover_tables()` rather than remembered. Its rows are
    # the 9 Pub 28 designators excluded as ordinary English that takes a
    # digit, each asserted to survive.
    "PUB28_EXCLUDED": [
        "addr/terminal-guard-shared",
        "addr/no-sep-branch-requires-digit",
    ],
    "SIGNATURE_LEAVE": [
        "sig/signatory-rejects-a-colon",
        "sig/signatory-word-cap",
        "sig/prose-stops-the-scan",
    ],
}


# Tables in the matrix modules that are NOT LEAVE tables, each with the reason.
# `--check-registry` requires every discovered table to appear either here or in
# TABLE_GUARDS: a table in neither is one nobody classified, and that is the
# case the gate exists for.
NOT_LEAVE_TABLES: dict[str, str] = {
    "ADDRESS_SHAPES_REDACT": "REDACT rows -- assert a real address IS removed",
    "SUFFIX_SHAPE": "REDACT rows",
    "SEPARATORS_REDACT": "REDACT rows",
    "POSITION": "REDACT rows",
    "RESIDUAL_OVER_REDACTED": "accepted OVER-redaction; asserts a changed output, not survival",
    "IDEMPOTENCE_CASES": "asserts a second pass is a no-op, not that a rule leaves text alone",
    "PHONE_REDACT": "REDACT rows",
    "CAGE_REDACT": "REDACT rows",
    "CONTRACT_REDACT": "REDACT rows",
    "SIGNATURE_REDACT": "REDACT rows",
    # This one is the reason the derivation exists. It is a DECISION table whose
    # 9 excluded designators are asserted to survive -- LEAVE rows in substance,
    # carried in a differently-shaped structure, and invisible to a hand list of
    # table names. Registered as LEAVE below via `pub28_excluded_rows()`.
    "PUB28_DESIGNATORS": "decision table; its LEAVE half is collected separately, see below",
}


def _original() -> str:
    return REDACT.read_text(encoding="utf-8")


def _line_containing(source: str, needle: str, occurrence: int = 0) -> str:
    hits = [ln for ln in source.split("\n") if needle in ln]
    if not hits:
        raise SystemExit(f"anchor not found in redact.py: {needle!r}")
    return hits[occurrence]


def build_mutations(source: str):
    """(name, old, new). Anchors are LIFTED from the file, never typed.

    Every anchor here is regex source. Typing one as a literal means writing
    backslashes through a shell, which this repo has a standing lesson about.
    """
    out = []

    def swap(name, needle, transform, occurrence=0):
        old = _line_containing(source, needle, occurrence)
        new = transform(old)
        if new == old:
            raise SystemExit(f"mutation {name} is a no-op on {old!r}")
        out.append((name, old, new))

    def neutralise(name, needle, occurrence=0):
        """Blank this guard's pattern, keeping the line and its operator.

        Composable, unlike dropping the line: these guards are lines in an
        implicit concatenation and several carry a leading `+`, so removing
        two at once leaves a dangling operator and the all-guards-off
        variant will not compile.
        """
        old = _line_containing(source, needle, occurrence)
        out.append((name, old, old[: old.index('r"')] + 'r""'))

    def drop(name, needle, occurrence=0, span=1):
        """Drop `span` consecutive lines from the one containing `needle`.

        `span` exists because the facility terminal guard is THREE lines. The
        first run of this tool dropped only the last, leaving `(?!` unterminated
        -- the regex would not compile, the mutation was skipped, and every row
        it should have killed was counted as `unrelated`. The tool inflated the
        number it was built to measure. `_evaluate` now treats a non-compiling
        mutation as a hard error rather than a skip.
        """
        lines = source.split("\n")
        i = lines.index(_line_containing(source, needle, occurrence))
        out.append((name, "\n".join(lines[i : i + span]) + "\n", ""))

    # --- address --------------------------------------------------------
    swap(
        "addr/street-sep-crosses-newline",
        "_STREET_SEP = _HSPACE",
        lambda s: '_STREET_SEP = r"' + BS + 's"',
    )
    swap(
        "addr/suite-sep-crosses-newline",
        "_SUITE_SEP = r",
        lambda s: s.replace('r"(?:" + _HSPACE + r"|', 'r"(?:' + BS + "s|"),
    )
    swap(
        "addr/suite-sep-abbrev-crosses-newline",
        "_SUITE_SEP_ABBREV = r",
        lambda s: s.replace('r"(?:" + _HSPACE + r"|', 'r"(?:' + BS + "s|"),
    )
    # One constant, three branches (facility, suite, city/state/ZIP) since
    # the B3/B9 fix. Removing it is one mutation now, not three.
    swap(
        "addr/terminal-guard-shared",
        "_NOT_FOLLOWED_BY_A_LOWERCASE_WORD = ",
        lambda s: '_NOT_FOLLOWED_BY_A_LOWERCASE_WORD = r""',
    )
    # The guard's case-scoping is its own guard: `[a-z]` inside an
    # IGNORECASE pattern blocks on ANY following word, which is how it
    # shipped in #139 and why `Suite 400 Arlington` stopped redacting when
    # the guard was extended.
    swap(
        "addr/terminal-guard-case-scoped",
        "_NOT_FOLLOWED_BY_A_LOWERCASE_WORD = ",
        lambda s: s.replace("(?-i:[a-z])", "[a-z]"),
    )
    swap(
        "addr/citystatezip-determiner-guard",
        "Those|Our|Their|Its|An?",
        lambda s: '    r"' + BS + 'b"',
    )
    swap(
        "addr/pre-keyword-ordinal-required",
        "_PRE_KEYWORD_PAT = r",
        lambda s: s.replace("(?:st|nd|rd|th)", "(?:st|nd|rd|th)?"),
    )
    swap("addr/roman-branch-case-scoped", "(?-i:[IVXL]", lambda s: s.replace("(?-i:", "(?:"))
    swap(
        "addr/no-sep-branch-requires-digit",
        'r"' + BS + "d[A-Za-z0-9" + BS + '-]*"',
        lambda s: s.replace('r"' + BS + "d[A-Za-z", 'r"[A-Za-z'),
    )
    swap("addr/letter-prefix-capped-at-3", "[A-Za-z]{0,3}", lambda s: s.replace("{0,3}", "{0,8}"))
    # B4: the street name and street word are scoped out of IGNORECASE, so
    # `one possible way` and `the 16 TB drive` stop parsing as addresses.
    swap(
        "addr/street-branch-case-scoped",
        "+){1,4}(?-i:",
        lambda s: s.replace("(?-i:", "(?:"),
    )
    swap(
        "addr/single-letter-refuses-when-number-follows",
        "+[A-Za-z0-9](?!",
        lambda s: s[: s.index("(?!")] + '"',
    )

    # --- phone ----------------------------------------------------------
    neutralise("phone/no-letter-before-a-phone", 'r"(?<![A-Za-z])"')
    neutralise("phone/leading-lookbehind", "(?<![" + BS + "d.")
    neutralise("phone/ipv4-guard", "(?!" + BS + "d{1,3}(?:")
    neutralise("phone/iso-date-guard", "(?!" + BS + "d{4}-")
    neutralise("phone/trailing-guard", 'r"(?![' + BS + "d" + BS + '-/])"')
    swap("phone/digit-count-7-to-15", "return 7 <= sum(", lambda s: "    return True")
    swap("phone/separator-is-hspace", "_PHONE_SEP = r", lambda s: '_PHONE_SEP = r"[ .-]"')
    swap(
        "phone/group-size-max-4",
        "_PHONE_GROUP = r",
        lambda s: s.replace("{1,4}", "{1,6}").replace("{0,4}", "{0,6}"),
    )
    swap(
        "phone/at-most-four-groups",
        '+ r"){1,3}"',
        lambda s: s.replace("){1,3}", "){1,5}"),
    )
    swap(
        "phone/shape-validator",
        "def _phone_shape_ok",
        lambda s: s + "\n    return True  # oracle mutation",
    )
    neutralise("phone/maximal-match-start", 'r"(?<!' + BS + 'd" + _PHONE_SEP')
    neutralise("phone/maximal-match-end", '+ r"(?!" + _PHONE_SEP + r"' + BS + 'd)"')

    # --- cage / contract / signature -------------------------------------
    swap(
        "cage/separator-is-hspace",
        "_CAGE_SEP = r",
        lambda s: '_CAGE_SEP = r"[' + BS + 's:#.,-]"',
    )
    swap(
        "cage/value-must-contain-a-digit",
        "(?=[A-Z0-9]{0,4}",
        lambda s: s.replace('r"(?=[A-Z0-9]{0,4}' + BS + 'd)" ', ""),
    )

    # `re.IGNORECASE,` on its own is not unique -- four patterns in this file
    # carry it, so the whole-line anchor matched four times and the run refused
    # to measure (correctly: a mutation applied to the wrong pattern would be
    # measuring something other than what its name says). Anchor on the
    # contract pattern line, which is unique, and take the block through the
    # flag.
    def _contract_block():
        lines = source.split("\n")
        i = lines.index(_line_containing(source, "_RE_CONTRACT = re.compile("))
        j = next(k for k in range(i, i + 12) if "re.IGNORECASE," in lines[k])
        old = "\n".join(lines[i : j + 1]) + "\n"
        return old, old.replace("    re.IGNORECASE,\n", "    0,\n")

    _old, _new = _contract_block()
    out.append(("contract/ignorecase", _old, _new))
    swap(
        "sig/signatory-rejects-a-colon",
        'if ":" in stripped:',
        lambda s: s.replace('if ":" in stripped:', "if False:"),
    )
    swap(
        "sig/signatory-word-cap",
        "1 <= len(words) <= _MAX_SIGNATORY_WORDS",
        lambda s: s.replace("_MAX_SIGNATORY_WORDS", "99"),
    )
    # B1's fix: the scan stops at the first SENTENCE instead of reaching
    # five lines for anything contact-shaped. Without it any IP address,
    # date or seven-digit run near a wrapped `Best` truncates the input.
    swap(
        "sig/prose-stops-the-scan",
        "def _looks_like_prose",
        lambda s: s + "\n    return False  # oracle mutation",
    )
    return out


def discover_tables() -> dict[str, int]:
    """Every module-level table in the two matrix modules, by introspection.

    Derived, not listed. A table added to either file appears here the moment it
    exists, so `--check-registry` fails until somebody classifies it -- which is
    the property a hand-written universe cannot have, and the reason the gate
    was reporting on 11 of 13 tables while claiming completeness.
    """
    for path in (str(REPO_APP), str(TESTS)):
        if path not in sys.path:
            sys.path.insert(0, path)
    import test_redact_address_matrix as M
    import test_redact_rules_matrix as N

    found: dict[str, int] = {}
    for module in (M, N):
        for name in dir(module):
            if not name.isupper() or name.startswith("_"):
                continue
            value = getattr(module, name)
            if isinstance(value, (list, tuple)) and value:
                found[name] = len(value)
    return found


def pub28_excluded_rows():
    """The LEAVE half of PUB28_DESIGNATORS, as (id, text) pairs.

    `test_excluded_pub28_designators_stay_excluded` asserts each excluded
    designator survives with a number after it. Those are LEAVE rows in
    substance; they were invisible to the oracle because the table they live in
    has a different shape and a name nobody had listed.
    """
    for path in (str(REPO_APP), str(TESTS)):
        if path not in sys.path:
            sys.path.insert(0, path)
    import test_redact_address_matrix as M

    return [(d, f"{d} 3") for d, covered, _why in M.PUB28_DESIGNATORS if not covered]


def leave_rows():
    """Every LEAVE row in both truth tables, as (table, id, text)."""
    for p in (str(REPO_APP), str(TESTS)):
        if p not in sys.path:
            sys.path.insert(0, p)
    import test_redact_address_matrix as M
    import test_redact_rules_matrix as N

    tables = (
        ("SUFFIX_SHAPE_PROSE", [(c[0], c[1]) for c in M.SUFFIX_SHAPE_PROSE]),
        ("POSITION_LEAVE", [(c[0], c[1]) for c in M.POSITION_LEAVE]),
        ("PRODUCT_NAMES", [(n, n) for n in M.PRODUCT_NAMES]),
        ("SECURITY_PROSE", [(t[:44], t) for t in M.SECURITY_PROSE]),
        ("STREET_NEWLINE_LEAVE", [(c[0], c[1]) for c in M.STREET_NEWLINE_LEAVE]),
        ("ADDRESS_SHAPES_LEAVE", [(c[0], c[1]) for c in M.ADDRESS_SHAPES_LEAVE]),
        ("RESIDUAL_LEAKED", [(c[0], c[1]) for c in M.RESIDUAL_LEAKED]),
        ("PHONE_LEAVE", [(c[0], c[1]) for c in N.PHONE_LEAVE]),
        ("CAGE_LEAVE", [(c[0], c[1]) for c in N.CAGE_LEAVE]),
        ("CONTRACT_LEAVE", [(c[0], c[1]) for c in N.CONTRACT_LEAVE]),
        ("SIGNATURE_LEAVE", [(c[0], c[1]) for c in N.SIGNATURE_LEAVE]),
        ("PUB28_EXCLUDED", pub28_excluded_rows()),
    )
    return [(table, rid, text) for table, pairs in tables for rid, text in pairs]


def _evaluate(rows):
    """Row keys whose text was ALTERED -- the LEAVE assertion would fail."""
    import app.ai.redact as R

    importlib.reload(R)
    failing = set()
    for table, rid, text in rows:
        out, _ = R.redact_for_ai(text, mode="strict")
        if out != text:
            failing.add((table, rid))
    return failing


def check_registry(rows) -> int:
    """The one property that can fail on input nobody configured.

    The universe is DISCOVERED from the matrix modules, not taken from the list
    being gated. An earlier version derived `found` from `leave_rows()` -- the
    same hand list it was checking -- so a table nobody had thought of was
    invisible to the gate AND to the oracle. Two were: `PUB28_DESIGNATORS` and
    the vertical-whitespace sweep. A gate whose universe is its own input can
    only ever confirm what somebody already wrote down.
    """
    discovered = discover_tables()
    unclassified = sorted(
        name for name in discovered if name not in TABLE_GUARDS and name not in NOT_LEAVE_TABLES
    )
    unguarded = sorted(t for t in TABLE_GUARDS if not TABLE_GUARDS[t])

    if unclassified or unguarded:
        print("leave-row-oracle: tables the registry cannot account for")
        print()
        for t in unclassified:
            print(f"  {t}: discovered in a matrix module, in neither TABLE_GUARDS")
            print("     nor NOT_LEAVE_TABLES -- nobody has said what it is.")
        for t in unguarded:
            print(f"  {t}: registered as a LEAVE table with an EMPTY guard list.")
        print()
        print("A table nobody classified reports clean, which makes")
        print('"I could not look" indistinguishable from "nothing to complain')
        print('about". Either register the guards it exercises in TABLE_GUARDS,')
        print("or declare it in NOT_LEAVE_TABLES with the reason it is not one.")
        return 1

    leave_count = len(TABLE_GUARDS)
    print(
        f"leave-row-oracle: registry clean ({len(discovered)} tables discovered; "
        f"{leave_count} LEAVE with guards, {len(NOT_LEAVE_TABLES)} declared not-LEAVE)"
    )
    return 0


def main(argv: list[str]) -> int:
    rows = leave_rows()
    if "--check-registry" in argv:
        return check_registry(rows)

    original = _original()
    REDACT.write_text(original, encoding="utf-8")
    if _evaluate(rows):
        print("leave-row-oracle: BASELINE NOT GREEN -- some LEAVE rows already fail.")
        print("Nothing measured. Fix the tree first; a red baseline makes every")
        print("mutation result meaningless.")
        return 2

    muts = build_mutations(original)
    print(f"baseline clean: {len(rows)} LEAVE rows across {len(TABLE_GUARDS)} tables")
    print(f"guards modelled: {len(muts)}")
    print()

    killed_by: dict = {}
    protected_alone: set = set()
    try:
        for name, old, new in muts:
            n = original.count(old)
            if n != 1:
                print(f"  !! {name}: anchor appears {n} times, not 1 -- cannot measure")
                return 2
            REDACT.write_text(original.replace(old, new), encoding="utf-8")
            try:
                failing = _evaluate(rows)
            except Exception as exc:
                # NOT a skip. A mutation that will not compile silently removes
                # a guard from the measurement and inflates `unrelated`.
                print(f"  !! {name} did not compile: {type(exc).__name__}: {str(exc)[:70]}")
                return 2
            print(f"  {name:48} flips {len(failing):3}")
            for key in failing:
                killed_by.setdefault(key, []).append(name)

        # All guards off at once. Whatever still survives THIS was never in the
        # risk class, so no guard could have been what saved it.
        mutated = original
        for _name, old, new in muts:
            mutated = mutated.replace(old, new)
        REDACT.write_text(mutated, encoding="utf-8")
        try:
            all_off_failing = _evaluate(rows)
        except Exception as exc:
            print(f"  !! all-guards-off variant did not compile: {type(exc).__name__}: {exc}")
            return 2

        # ALL GUARDS OFF EXCEPT ONE, for each guard in turn. A row that survives
        # such a variant is protected by that guard ALONE, which separates
        # "defended in depth by several guards" from "pinning nothing".
        #
        # Without this the oracle PUNISHES redundant protection, and it did:
        # after the B3/B9 fix, `Flat network segmentation is the core finding`
        # is protected by the no-separator digit requirement AND by the shared
        # terminal guard, so removing either alone leaves the other -- and the
        # row was reported as pinning nothing on the round it became strictly
        # safer. Found by running the tool on the rewritten rules.
        #
        # One run per guard, not per row.
        for keep_name, _old, _new in muts:
            variant = original
            for name, old, new in muts:
                if name != keep_name:
                    variant = variant.replace(old, new)
            REDACT.write_text(variant, encoding="utf-8")
            try:
                failing = _evaluate(rows)
            except Exception:
                # Tells us nothing about any row. Skipping can only UNDER-count
                # protection, never invent it -- but say so out loud.
                print(f"  (all-but-{keep_name} did not compile; skipped)")
                continue
            for table, rid, _text in rows:
                key = (table, rid)
                if key in all_off_failing and key not in failing:
                    protected_alone.add(key)
    finally:
        # NOT `return 2` here: a return inside `finally` swallows any exception
        # still propagating, which would turn "the oracle crashed" into "the
        # oracle reported 2" and lose the traceback. Record it and act below.
        REDACT.write_text(original, encoding="utf-8")
        restore_failed = _original() != original

    if restore_failed:
        print("*** RESTORE FAILED -- redact.py is NOT as it was found ***")
        print("Do not trust the working tree. `git checkout -- apps/api/app/ai/redact.py`.")
        return 2

    print()
    print(f"  {'ALL GUARDS OFF AT ONCE':48} flips {len(all_off_failing):3}")
    print()

    load_bearing = set(killed_by)
    classes = {}
    for table, rid, _text in rows:
        key = (table, rid)
        if key in load_bearing:
            classes[key] = "load-bearing"
        elif key not in all_off_failing:
            classes[key] = "negative-control"
        elif key in protected_alone:
            classes[key] = "defended-in-depth"
        else:
            classes[key] = "unrelated"

    counts = {
        c: sum(1 for v in classes.values() if v == c)
        for c in ("load-bearing", "defended-in-depth", "unrelated", "negative-control")
    }
    total = len(rows)
    risk = total - counts["negative-control"]
    print(f"LEAVE rows:                       {total}")
    print(f"  load-bearing:                   {counts['load-bearing']}")
    print(f"  defended-in-depth:              {counts['defended-in-depth']}")
    print(f"  unrelated:                      {counts['unrelated']}")
    print(f"  negative-control-by-design:     {counts['negative-control']}")
    print()
    pct = 100.0 * counts["unrelated"] / risk if risk else 0.0
    print(f"UNRELATED / IN-RISK-CLASS:        {counts['unrelated']}/{risk} = {pct:.1f}%")
    print("(negative controls are excluded from the denominator by DERIVATION --")
    print(" they survive the all-guards-off variant, so no guard was ever their")
    print(" reason. This is an upper bound; see the module docstring.)")
    print()

    print("=== per table ===")
    for table in sorted({t for t, _, _ in rows}):
        keys = [(t, r) for t, r, _ in rows if t == table]
        lb = sum(1 for k in keys if classes[k] == "load-bearing")
        dd = sum(1 for k in keys if classes[k] == "defended-in-depth")
        un = sum(1 for k in keys if classes[k] == "unrelated")
        nc = sum(1 for k in keys if classes[k] == "negative-control")
        flag = "  <-- REVIEW" if un else ""
        print(
            f"  {table:22} {len(keys):3} rows  {lb:3} bearing {dd:3} depth "
            f"{un:3} unrelated {nc:3} neg{flag}"
        )

    print()
    print("=== rows in the risk class that no single guard pins ===")
    for table, rid, _text in rows:
        if classes[(table, rid)] == "unrelated":
            print(f"  [{table}] {rid!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
