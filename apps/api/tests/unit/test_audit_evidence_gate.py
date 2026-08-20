"""The merge gate that makes skipping the adversarial audit deliberate (§14).

#93, #94 and #95 each merged green with the gate silently skipped, and each put
a defect on `main` that the audit found afterwards — including a client-facing
fabricated gap. The first proposed fix was to document the gate in `CLAUDE.md`,
which is a discipline fix, and discipline against this exact shape has failed
nine recorded times (#72). This is the structural version.
"""

from __future__ import annotations

import pytest
from scripts.check_audit_evidence import is_code_change, missing_evidence

_GOOD = """Some description.

## Adversarial audit

Reviewer: adversarial-reviewer
Findings: 2 confirmed, 1 plausible
Disposition: both fixed here; the plausible one filed as #101
"""


# --- what counts as a code change ------------------------------------------


@pytest.mark.unit
def test_a_documentation_only_change_is_exempt() -> None:
    """#88 and #91 were pure docs — the one defensible skip.

    `CLAUDE.md` was in this list and has been removed: it governs how every
    session behaves, so it is operative configuration rather than prose, and
    `test_the_reviewer_agents_own_definition_is_not_exempt` now pins that. The
    narrowing is the point of the fix, not a weakening of this test.
    """
    assert is_code_change(["CONTEXT.md", "DECISIONS.md", "context/gene.md"]) is False


@pytest.mark.unit
def test_a_source_change_needs_an_audit() -> None:
    assert is_code_change(["apps/api/app/routes/attack.py"]) is True


@pytest.mark.unit
def test_a_test_only_change_needs_an_audit() -> None:
    """A test change alters what the suite proves. #93's whole subject was a
    test that could not fail."""
    assert is_code_change(["apps/api/tests/unit/test_x.py"]) is True


@pytest.mark.unit
def test_a_workflow_change_needs_an_audit() -> None:
    """Changing the gates themselves is exactly when review matters most."""
    assert is_code_change([".github/workflows/ci.yml"]) is True


@pytest.mark.unit
def test_docs_mixed_with_code_still_needs_an_audit() -> None:
    """Otherwise adding a README to a code PR would buy an exemption."""
    assert is_code_change(["DECISIONS.md", "apps/api/app/ai/engine.py"]) is True


@pytest.mark.unit
def test_an_unrecognised_path_defaults_to_needing_an_audit() -> None:
    """The default is "this needs review", so a new directory is covered
    without anyone remembering to add it to a list."""
    assert is_code_change(["some/new/thing.rb"]) is True


# --- what counts as evidence ------------------------------------------------


@pytest.mark.unit
def test_a_complete_audit_block_passes() -> None:
    assert missing_evidence(_GOOD) == []


@pytest.mark.unit
def test_a_body_with_no_audit_section_is_refused() -> None:
    problems = missing_evidence("Just a description of the change.")
    assert len(problems) == 3


@pytest.mark.unit
def test_findings_none_is_a_valid_answer() -> None:
    """A clean audit is a real outcome. Refusing it would push people toward
    inventing findings, which is worse than none."""
    body = "## Adversarial audit\nFindings: none\nDisposition: nothing to act on\n"
    assert missing_evidence(body) == []


@pytest.mark.unit
def test_findings_without_a_disposition_is_refused() -> None:
    """Listing findings and not saying what happened to them is how a known
    defect ships anyway."""
    body = "## Adversarial audit\nFindings: 3 confirmed\n"
    assert missing_evidence(body) == ['no "Disposition:" line (what happened to each finding)']


@pytest.mark.unit
def test_an_empty_findings_value_is_not_evidence() -> None:
    body = "## Adversarial audit\nFindings:\nDisposition:\n"
    assert len(missing_evidence(body)) == 2


@pytest.mark.unit
def test_the_heading_is_matched_case_insensitively_and_at_any_level() -> None:
    for heading in ("# ADVERSARIAL AUDIT", "### Adversarial Audit", "## adversarial audit"):
        body = f"{heading}\nFindings: none\nDisposition: none\n"
        assert missing_evidence(body) == [], heading


@pytest.mark.unit
def test_a_bulleted_block_is_accepted() -> None:
    """People write PR bodies as lists; refusing that teaches them to fight the
    gate rather than use it."""
    body = "## Adversarial audit\n\n- Reviewer: adversarial-reviewer\n- Findings: none\n- Disposition: n/a\n"
    assert missing_evidence(body) == []


@pytest.mark.unit
def test_merely_mentioning_the_words_is_not_evidence() -> None:
    """The check is weak by design — it proves a claim was RECORDED, not that an
    audit happened. It must at least require the structure, or it proves
    nothing at all."""
    body = "I ran an adversarial audit and it was fine.\n"
    assert missing_evidence(body) != []


# --- findings from the adversarial audit of this gate -----------------------


@pytest.mark.unit
def test_bold_labels_are_accepted() -> None:
    """`**Findings:** none` is this repo's dominant prose style, and the first
    version REJECTED it — printing 'no "Findings:" line' over a body that
    visibly contained one. A check that tells an author something false about
    their own text teaches them to fight the gate."""
    body = (
        "## **Adversarial audit**\n"
        "- **Reviewer:** adversarial-reviewer\n"
        "- **Findings:** 2 confirmed\n"
        "- **Disposition:** both fixed here\n"
    )
    assert missing_evidence(body) == []


@pytest.mark.unit
def test_the_error_messages_own_example_does_not_satisfy_the_gate() -> None:
    """Pins a property that was accidental until the audit noticed it.

    The example in the stderr help is indented four spaces, which is a markdown
    code block, and HEADING allows at most three. So pasting the error message
    back into a PR body does NOT pass. Reformatting that example flush-left
    would silently turn the gate's own output into a valid bypass.
    """
    from scripts.check_audit_evidence import main as _main  # noqa: F401

    example = (
        "    ## Adversarial audit\n"
        "    Reviewer: adversarial-reviewer\n"
        "    Findings: none\n"
        "    Disposition: nothing to act on\n"
    )
    assert missing_evidence(example) != []


@pytest.mark.unit
def test_the_reviewer_agents_own_definition_is_not_exempt() -> None:
    """`.claude/agents/adversarial-reviewer.md` IS the reviewer this gate
    enforces. Exempting it as "a .md file" would let the mechanism that catches
    the next #93 be rewritten with no audit."""
    assert is_code_change([".claude/agents/adversarial-reviewer.md"]) is True
    assert is_code_change(["CLAUDE.md"]) is True


# --- main(): the entry point CI actually runs -------------------------------
#
# Every test above calls the two helpers directly. `main` — including the
# exit-1 that makes this a gate at all — had NO coverage: inverting `return 1`
# to `return 0`, or swapping the two file reads, left the whole suite green
# while the gate passed on every PR. The #72 shape, in the #72-adjacent gate.


def _files(tmp_path, paths: str, body: str):
    p = tmp_path / "changed.txt"
    b = tmp_path / "body.md"
    p.write_text(paths, encoding="utf-8")
    b.write_text(body, encoding="utf-8")
    return ["--changed-files", str(p), "--body", str(b)]


@pytest.mark.unit
def test_main_exits_nonzero_for_a_code_change_with_no_evidence(tmp_path) -> None:
    from scripts.check_audit_evidence import main

    assert main(_files(tmp_path, "apps/api/app/x.py\n", "just a description\n")) == 1


@pytest.mark.unit
def test_main_exits_zero_when_the_audit_is_recorded(tmp_path) -> None:
    from scripts.check_audit_evidence import main

    body = "## Adversarial audit\nFindings: none\nDisposition: nothing to act on\n"
    assert main(_files(tmp_path, "apps/api/app/x.py\n", body)) == 0


@pytest.mark.unit
def test_main_exits_zero_for_a_documentation_only_change(tmp_path) -> None:
    from scripts.check_audit_evidence import main

    assert main(_files(tmp_path, "CONTEXT.md\ncontext/gene.md\n", "no audit here\n")) == 0


@pytest.mark.unit
def test_main_refuses_rather_than_exempting_when_no_paths_were_collected(tmp_path) -> None:
    """Fails CLOSED. An empty list previously printed "documentation-only
    change, exempt" — a green gate with a positive message, from input that
    supports neither reading."""
    from scripts.check_audit_evidence import main

    assert main(_files(tmp_path, "", "anything\n")) == 2
    assert main(_files(tmp_path, "\n  \n", "anything\n")) == 2
