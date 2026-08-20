"""W8a: the mechanised sweep for tests that cannot fail (#72).

Nine recorded instances of a test that passes whether or not the fix it guards
is present. The rule has been in `CLAUDE.md` since instance 2 and instances 8
and 9 were still written by someone who had read it that day — so the mechanism
is the deliverable, not the reminder.

This is TIER 1: static, cheap, blocking. It catches a MINORITY of the class and
says so; the tier that covers the class is diff-scoped mutation testing, which
runs on a schedule rather than as a gate. Claiming this file closes #72 would
itself be the #72 pattern one level up.

Two signals, both derived from real instances:

- **TI001** — a test importing a private name from the module it tests. Instance
  1 (`test_csf_ai_contract.py` building its "prompt-compliant" body out of the
  parser's own `_DIM_FIELDS`) is exactly this shape. It is a signal, not a
  verdict: importing `_CSF_SCORE_PROMPT` in that same file is CORRECT, because a
  contract test must read the spec it checks against. So TI001 demands a written
  justification rather than forbidding the import.
- **TI002** — a containment assertion whose needle carries no literal context.
  Instance 8 was `str(dash["total_gap_count"]) in doc_summary`, satisfied by the
  coverage fraction `106/106 subcategories scored`. The fix was to assert
  `f"{n} gap(s) at target T4"`. That difference — interpolated value ALONE vs.
  interpolated value ANCHORED IN LITERAL TEXT — is precisely the defect, and is
  cheap to detect.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.check_test_integrity import Finding, scan_source

# --- TI001: private imports from the module under test ---------------------


@pytest.mark.unit
def test_a_private_CALLABLE_import_is_not_flagged() -> None:
    """`_llm_dep` / `_storage_dep` are FastAPI dependency-override keys.

    Importing one says nothing about what the test asserts. Flagging every
    private name gives 41 findings on this tree, 36 of them override handles;
    restricting to constant-style names gives 5, all of the instance-1 shape.
    A rule whose signal is 12% of its output gets muted, and a muted rule is
    worth nothing.
    """
    src = "from app.routes.zt import _llm_dep\n"
    assert scan_source("tests/unit/test_x.py", src) == []


@pytest.mark.unit
def test_flags_a_private_import_from_an_app_module() -> None:
    src = "from app.routes.csf import _DIM_FIELDS\n"
    findings = scan_source("tests/unit/test_x.py", src)
    assert [f.code for f in findings] == ["TI001"]
    assert "_DIM_FIELDS" in findings[0].message


@pytest.mark.unit
def test_a_justified_private_import_is_accepted() -> None:
    """The point is a written reason, not a ban.

    Importing the PROMPT into a contract test is correct — the prompt is the
    spec. Importing the PARSER's field names to build the expected value is the
    defect. No static rule separates those, so the checker demands that whoever
    writes it says which one it is.
    """
    src = (
        "# test-integrity: the prompt IS the spec this test checks against\n"
        "from app.ai.jobs import _CSF_SCORE_PROMPT\n"
    )
    assert scan_source("tests/unit/test_x.py", src) == []


@pytest.mark.unit
def test_same_line_justification_is_accepted() -> None:
    src = "from app.routes.risk import _RISK_BATCH_SIZE  # test-integrity: sizing only\n"
    assert scan_source("tests/unit/test_x.py", src) == []


@pytest.mark.unit
def test_a_multi_line_justification_block_is_accepted() -> None:
    """A reason worth demanding is usually a paragraph, not one line.

    The first version only looked at the immediately-preceding line, so every
    real justification written for this checker's own first run was rejected —
    the marker was at the TOP of a four-line explanation. Requiring it to be the
    last line would have taught people to write one-line reasons.
    """
    src = (
        "# test-integrity: the static half derives parser keys and checks them\n"
        "# against the prompt, which is sound; the e2e half agrees by\n"
        "# construction and is tracked as #92.\n"
        "from app.routes.csf import _DIM_FIELDS\n"
    )
    assert scan_source("tests/unit/test_x.py", src) == []


@pytest.mark.unit
def test_a_comment_block_without_the_marker_is_not_a_justification() -> None:
    src = "# just an ordinary comment\n# explaining something else\nfrom app.routes.csf import _DIM_FIELDS\n"
    assert [f.code for f in scan_source("tests/unit/test_x.py", src)] == ["TI001"]


@pytest.mark.unit
def test_an_empty_justification_is_not_a_justification() -> None:
    src = "# test-integrity:\nfrom app.routes.csf import _DIM_FIELDS\n"
    findings = scan_source("tests/unit/test_x.py", src)
    assert [f.code for f in findings] == ["TI001"]


@pytest.mark.unit
def test_private_imports_from_test_helpers_are_not_flagged() -> None:
    """`scripts._common` is a shared test helper, not the module under test.

    Counting these was how the first estimate of this rule's noise came out at
    5 hits instead of 4.
    """
    src = "from scripts._common import something\nfrom ._helpers import _build\n"
    assert scan_source("tests/unit/test_x.py", src) == []


@pytest.mark.unit
def test_public_imports_are_not_flagged() -> None:
    src = "from app.routes.csf import finalize_csf_deliverable\n"
    assert scan_source("tests/unit/test_x.py", src) == []


# --- TI002: containment assertions with no literal anchor ------------------


@pytest.mark.unit
def test_flags_a_bare_stringified_value_in_a_containment_assertion() -> None:
    """Instance 8, reduced to its shape."""
    src = 'def test_a():\n    assert str(dash["total_gap_count"]) in doc_summary\n'
    findings = scan_source("tests/unit/test_x.py", src)
    assert [f.code for f in findings] == ["TI002"]


@pytest.mark.unit
def test_flags_an_fstring_that_is_only_a_placeholder() -> None:
    src = 'def test_a():\n    assert f"{total}" in blob\n'
    assert [f.code for f in scan_source("tests/unit/test_x.py", src)] == ["TI002"]


@pytest.mark.unit
def test_accepts_an_interpolated_value_anchored_in_literal_text() -> None:
    """The fix applied to instance 8 must not itself be flagged."""
    src = 'def test_a():\n    assert f"{n} gap(s) at target T4" in doc_summary\n'
    assert scan_source("tests/unit/test_x.py", src) == []


@pytest.mark.unit
def test_accepts_a_plain_string_literal_needle() -> None:
    src = 'def test_a():\n    assert "at target S4" in summary\n'
    assert scan_source("tests/unit/test_x.py", src) == []


@pytest.mark.unit
def test_a_bare_name_needle_is_NOT_flagged() -> None:
    """This assertion was written the other way round first, and was wrong.

    It demanded that `assert total in blob` be flagged. That cannot be
    distinguished from `key in mapping` or `code in some_set` without type
    information, and measured on this tree **36 of 38** such assertions are
    collection membership. Shipping it would have produced a rule whose output
    was overwhelmingly noise — which gets muted, and a muted rule is worth
    nothing.

    Both recorded instances of this defect wrote `str(...)` explicitly, so
    explicit stringification is the fingerprint worth flagging. Narrowing to it
    keeps every real hit and drops every false one.
    """
    src = "def test_a():\n    assert total in blob\n"
    assert scan_source("tests/unit/test_x.py", src) == []


@pytest.mark.unit
def test_membership_in_a_collection_is_not_flagged() -> None:
    """`x in [a, b]` and `x in {…}` are set membership, not substring search.

    Only string-haystack containment can be satisfied by an unrelated
    coincidence, which is the entire defect.
    """
    src = (
        "def test_a():\n"
        "    assert code in {'a', 'b'}\n"
        "    assert code in [1, 2]\n"
        "    assert key in mapping\n"
    )
    assert scan_source("tests/unit/test_x.py", src) == []


@pytest.mark.unit
def test_not_in_assertions_are_not_flagged() -> None:
    """`not in` cannot pass by coincidence — a stray match makes it FAIL.

    The failure direction is the opposite one, so it is not this defect.
    """
    src = "def test_a():\n    assert str(total) not in blob\n"
    assert scan_source("tests/unit/test_x.py", src) == []


@pytest.mark.unit
def test_a_justified_containment_assertion_is_accepted() -> None:
    src = (
        "def test_a():\n"
        "    # test-integrity: the sheet has no other numeric cell, verified red-on-revert\n"
        "    assert str(total) in blob\n"
    )
    assert scan_source("tests/unit/test_x.py", src) == []


# --- the checker over the real tree ----------------------------------------


@pytest.mark.unit
def test_the_repo_is_clean_or_every_exception_is_justified() -> None:
    """The gate itself. Every finding must be fixed or carry a written reason.

    This is the assertion that makes the checker a mechanism rather than a
    report nobody reads.
    """
    from scripts.check_test_integrity import scan_tree

    root = Path(__file__).resolve().parents[1]
    findings = scan_tree(root)
    assert findings == [], "unjustified test-integrity findings:\n" + "\n".join(
        f"  {f.path}:{f.line} {f.code} {f.message}" for f in findings
    )


@pytest.mark.unit
def test_finding_is_comparable_by_value() -> None:
    a = Finding(path="p", line=1, code="TI001", message="m")
    b = Finding(path="p", line=1, code="TI001", message="m")
    assert a == b
