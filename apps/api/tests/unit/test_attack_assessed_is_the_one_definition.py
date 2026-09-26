"""#621 round 2: ONE definition of the assessed set and of "scored".

Finding 3: `coverage.ASSESSED` had no reader. `analytics.compute`, the client
dashboard's `total_evaluated` and the exporters each wrote covered + partial +
gap by hand, so the constant documented a rule nothing followed. The sites now
sum over `ASSESSED`, and the first test here fails on a hand-written sum
anywhere under `app/` -- a new site included, which a list of call sites would
not catch.

Finding 1: "scored" meant two populations in two client documents. The ATT&CK
deliverable counted `unable_to_determine` as scored; the Risk Register's
citable scope did not. Both now read `coverage.UNJUDGED`, and the last test
pins the two counts as equal over one row of every status.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.attack import analytics
from app.attack.analytics import compute
from app.attack.catalog import TECHNIQUES
from app.attack.coverage import ASSESSED, CoverageStatus
from app.models.attack_assessment import AttackCoverage
from app.risk.link_scope import scope_for
from tests._attack_rows import standalone_rows

APP = Path(__file__).resolve().parents[2] / "app"

# Literal, not derived from ASSESSED: this is the spelling the guard hunts for.
_SUMMED = {"covered", "partial", "gap"}


def _name(node: ast.AST) -> str | None:
    """`covered` from `t.covered`, `counts["covered"]`,
    `counts[CoverageStatus.COVERED.value]` or `covered`."""
    if isinstance(node, ast.Attribute):
        if node.attr == "value":
            return _name(node.value)
        return node.attr.lower()
    if isinstance(node, ast.Subscript):
        key = node.slice
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            return key.value.lower()
        return _name(key)
    if isinstance(node, ast.Name):
        return node.id.lower()
    return None


def _operands(node: ast.AST) -> list[ast.AST]:
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _operands(node.left) + _operands(node.right)
    return [node]


def _hand_written_sums(tree: ast.AST) -> list[int]:
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            names = {_name(o) for o in _operands(node)}
            if names >= _SUMMED:
                hits.append(node.lineno)
    return hits


@pytest.mark.unit
def test_the_guard_can_see_a_hand_written_sum() -> None:
    # Asserted FIRST: a detector that matches nothing passes the scan below
    # over every file.
    for src in (
        "x = t.covered + t.partial + t.gap",
        'x = c["covered"] + c["partial"] + c["gap"] + c["pending_review"]',
        "x = c[S.COVERED.value] + c[S.PARTIAL.value] + c[S.GAP.value]",
    ):
        assert _hand_written_sums(ast.parse(src)), src
    assert not _hand_written_sums(ast.parse("x = t.covered + 0.5 * t.partial"))


@pytest.mark.unit
def test_nothing_under_app_restates_the_assessed_set() -> None:
    files = sorted(APP.rglob("*.py"))
    assert len(files) > 50, f"scanned {len(files)} files under {APP}: wrong root?"
    offenders = [
        f"{path.relative_to(APP)}:{line}"
        for path in files
        for line in _hand_written_sums(ast.parse(path.read_text(encoding="utf-8")))
    ]
    assert (
        offenders == []
    ), "sum over `coverage.ASSESSED` instead of writing covered + partial + gap: " + ", ".join(
        offenders
    )


@pytest.mark.unit
def test_compute_takes_its_denominator_from_assessed(monkeypatch) -> None:
    """Behavioural half: widening ASSESSED must move the percentage. A compute
    that went back to a hand-written denominator would not notice."""
    covered, na = (
        r["technique_code"]
        for r in standalone_rows([{"technique_code": t.id} for t in TECHNIQUES], 2)
    )
    statuses = {covered: "covered", na: "not_applicable"}
    assert compute(statuses).coverage_pct == 100.0
    monkeypatch.setattr(analytics, "ASSESSED", ASSESSED | {CoverageStatus.NOT_APPLICABLE})
    assert compute(statuses).coverage_pct == 50.0


def _one_row_per_status() -> dict[str, str | None]:
    rows = standalone_rows([{"technique_code": t.id} for t in TECHNIQUES], len(CoverageStatus) + 1)
    codes = [r["technique_code"] for r in rows]
    out: dict[str, str | None] = {
        c: s.value for c, s in zip(codes[:-1], CoverageStatus, strict=True)
    }
    out[codes[-1]] = None  # and one unscored row
    return out


@pytest.mark.unit
def test_scored_means_the_same_rows_in_both_documents() -> None:
    statuses = _one_row_per_status()
    rows = [SimpleNamespace(technique_code=c, status=s) for c, s in statuses.items()]
    risk_scored = len(scope_for(AttackCoverage, rows).codes)
    assert compute(statuses).scored_count == risk_scored
    # And the number is the one the rule gives: the six statuses less
    # unable_to_determine. A literal, so this test does not read the constant
    # it is checking.
    assert risk_scored == 5


@pytest.mark.unit
def test_the_scored_total_is_the_old_one_whenever_nothing_is_unverified() -> None:
    """Condition 1 of the coordinator's verdict. `catalogue_count` replaced
    scored + unscored as the "Y" of "Scored: X/Y". On any assessment with no
    unable_to_determine row the two must be EXACTLY equal, so the change is a
    no-op on every assessment that exists today (no writer can produce the
    status: `coverage.WRITABLE`)."""
    statuses = {k: v for k, v in _one_row_per_status().items() if v != "unable_to_determine"}
    for sample in ({}, statuses):
        r = compute(sample)
        assert r.catalogue_count == r.scored_count + r.unscored_count
    r = compute(_one_row_per_status())
    assert r.catalogue_count == r.scored_count + r.unscored_count + r.unable_to_determine
