"""On a merge-queue entry the audit must name the head being merged (#659, #736 C).

`check_audit_evidence --head-sha FILE` is passed on merge_group only. FILE holds
the queued PR's current head, which the resolver has already shown is what the
group merges. The `## Adversarial audit` section must then contain a hex token
of 7 to 40 characters that is a prefix of that head.

Derived from practice, not from the parser: across the 20 most recent merged
PRs (1039 to 1162), every audit section named the final head this way (measured 2026-10-15
with `gh pr list --state merged --limit 20 --json number,headRefOid,body`, 20
of 20), while only 12 of 20 named it on the `Scope:` line. So the rule reads
the SECTION, and requires nothing the recent merges did not already do.

It is an attestation, like `Findings:` and `Disposition:`: it proves the audit
names the merged head, not that a reviewer read it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import scripts.check_audit_evidence as gate

HEAD = "13af17d5beafd86aba93c792c6e10a29e61f142b"


def _body(scope: str, *, before: str = "", after: str = "") -> str:
    return (
        f"## Summary\n{before}\n\n"
        "## Adversarial audit\n"
        "Findings: none\n"
        "Disposition: nothing to act on\n"
        f"Scope: {scope}\n"
        f"{after}"
    )


def _run(tmp_path: Path, body: str, head: str | None = HEAD) -> int:
    (tmp_path / "changed.txt").write_text("apps/api/app/x.py\n", encoding="utf-8")
    (tmp_path / "body.md").write_text(body, encoding="utf-8")
    argv = ["--changed-files", str(tmp_path / "changed.txt"), "--body", str(tmp_path / "body.md")]
    if head is not None:
        (tmp_path / "head.txt").write_text(f"{head}\n", encoding="utf-8")
        argv += ["--head-sha", str(tmp_path / "head.txt")]
    return gate.main(argv)


@pytest.mark.unit
@pytest.mark.parametrize(
    "scope",
    [
        "reviewed at 13af17d from ../review-13af17d (detached worktree)",
        "reviewed at `13af17d5`",
        f"final head {HEAD}",
        "rounds at d9d7c59 and 13AF17D5BEAF",
    ],
)
def test_an_audit_naming_the_head_passes(tmp_path, scope, capsys) -> None:
    assert _run(tmp_path, _body(scope)) == 0
    assert f"names the queued head {HEAD[:12]}" in capsys.readouterr().out


@pytest.mark.unit
def test_the_head_named_on_a_later_line_of_the_section_passes(tmp_path) -> None:
    body = _body("round 1 at d9d7c59", after="Final head 13af17d5 = d9d7c59 plus status docs.\n")
    assert _run(tmp_path, body) == 0


@pytest.mark.unit
@pytest.mark.parametrize(
    "scope",
    [
        "reviewed at d9d7c59",  # an earlier head
        "reviewed at 13af17",  # six characters: too short to name anything
        "reviewed at 13af17d6",  # a prefix that diverges
        "reviewed at x13af17d",  # glued to a word: not a sha token
        "reviewed at the final head",
    ],
)
def test_an_audit_not_naming_the_head_fails(tmp_path, scope, capsys) -> None:
    assert _run(tmp_path, _body(scope)) == 1
    assert "does not name the head being merged" in capsys.readouterr().err


@pytest.mark.unit
def test_a_subheading_inside_the_section_does_not_end_it(tmp_path) -> None:
    body = _body("round 1 at d9d7c59", after="\n### Round 2\nreviewed at 13af17d5\n")
    assert _run(tmp_path, body) == 0


@pytest.mark.unit
def test_the_head_named_only_outside_the_audit_section_fails(tmp_path) -> None:
    """A summary line mentioning the head is not the audit naming it."""
    body = _body(
        "reviewed at d9d7c59", before=f"Head is {HEAD}.", after="\n## Test plan\n13af17d\n"
    )
    assert _run(tmp_path, body) == 1


@pytest.mark.unit
@pytest.mark.parametrize("head", ["", "13af17d", HEAD.upper(), HEAD + "0", "not hex"])
def test_an_unreadable_head_file_is_could_not_look(tmp_path, head, capsys) -> None:
    assert _run(tmp_path, _body(f"at {HEAD}"), head=head) == 2
    assert "--head-sha" in capsys.readouterr().err


@pytest.mark.unit
def test_a_missing_head_file_is_could_not_look(tmp_path) -> None:
    body = _body(f"at {HEAD}")
    (tmp_path / "changed.txt").write_text("apps/api/app/x.py\n", encoding="utf-8")
    (tmp_path / "body.md").write_text(body, encoding="utf-8")
    argv = ["--changed-files", str(tmp_path / "changed.txt"), "--body", str(tmp_path / "body.md")]
    assert gate.main([*argv, "--head-sha", str(tmp_path / "absent.txt")]) == 2


@pytest.mark.unit
def test_without_head_sha_the_rule_does_not_apply(tmp_path) -> None:
    """pull_request runs pass no --head-sha; today's gate is unchanged there."""
    assert _run(tmp_path, _body("reviewed at d9d7c59"), head=None) == 0


@pytest.mark.unit
def test_a_documentation_only_change_stays_exempt(tmp_path) -> None:
    (tmp_path / "changed.txt").write_text("docs/x.md\n", encoding="utf-8")
    (tmp_path / "body.md").write_text("", encoding="utf-8")
    (tmp_path / "head.txt").write_text(f"{HEAD}\n", encoding="utf-8")
    argv = [
        "--changed-files",
        str(tmp_path / "changed.txt"),
        "--body",
        str(tmp_path / "body.md"),
        "--head-sha",
        str(tmp_path / "head.txt"),
    ]
    assert gate.main(argv) == 0


@pytest.mark.unit
def test_a_missing_audit_still_reports_the_missing_lines_first(tmp_path, capsys) -> None:
    assert _run(tmp_path, "## Summary\nnothing\n") == 1
    err = capsys.readouterr().err
    assert 'no "## Adversarial audit" section' in err
    assert "does not name the head being merged" in err
