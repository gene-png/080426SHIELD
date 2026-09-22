"""The link universe for risk synthesis: codes the client's assessments SCORED.

## What this exists to fix (#403)

`routes/risk.py` sends the synthesis model two allow-lists and its own docstring
states their purpose: *"what stop the model citing a technique or control the
client's assessments never contained."* Three constructions did not implement
that sentence. They were built from EVERY row of each assessment, and every row
is pre-seeded:

  * `provisioning.py` creates a `CsfAnswer` for every `SUBCATEGORIES` entry and
    a `ZtAnswer` for every capability at auto-provision time, neither carrying a
    tier or a stage.
  * `routes/attack.py` creates an `AttackCoverage` with `status=None` for every
    technique in the catalog.
  * nothing under `apps/api/app` deletes a row from any of the three tables.

So "present in the assessment" was true of the entire catalog on the day the
service was provisioned, and the allow-list meant *every code that exists*. A
model citing a control the consultant never looked at was accepted, persisted,
and rendered into the client's deliverable by `risk/exporters.py`.

## The predicate, per service, taken from what the model STORES

A row is in scope when the consultant recorded a judgement on it. The column
that carries the judgement differs per service, so it is named per service in
`SCORE_COLUMNS` below -- ONE table, consulted by one implementation, because
three copies is how three services come to disagree about one client. That is
the argument `routes/risk.py` already makes at its `resolve_target_tier` import
site, applied to the same file's other shared quantity.

**`status` is scored when it is not NULL, INCLUDING `not_applicable`.** That is
a judgement a consultant entered, not an absence, so a technique ruled
inapplicable stays citable. The distinction matters because it is the one place
the predicate is not simply "is there a number here".

## Both halves are returned, and that is the disclosure

`LinkScope` carries the excluded count as well as the codes. A helper that
returned only the codes would narrow the allow-list and leave nobody able to say
why links went sparse -- replacing a silently wrong citation with a silently
missing one, which `CLAUDE.md` names as the worse of the two. The count is what
the register's banner and the client's export render.

**`total` is the row count, not the catalog size.** An assessment holds the
catalog it was provisioned against; a later catalog addition does not retroact,
so dividing by `len(SUBCATEGORIES)` would report a denominator this client's
assessment never had.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.models.attack_assessment import AttackCoverage
from app.models.csf_assessment import CsfAnswer
from app.models.zt_assessment import ZtAnswer

#: `model -> (code column, judgement column)`.
#:
#: Keyed on the MODEL CLASS rather than on a service name string, so a caller
#: cannot ask for a scope under the wrong service's columns: it passes the model
#: it already queried. A fourth service is one row here and no new code.
#:
#: Verified cycle-free before adding these imports: nothing under `app/models`
#: imports `app.risk`, and `app/risk` imported no model before this file.
SCORE_COLUMNS: dict[type, tuple[str, str]] = {
    AttackCoverage: ("technique_code", "status"),
    CsfAnswer: ("subcategory_code", "maturity_tier"),
    ZtAnswer: ("capability_code", "maturity_stage"),
}


@dataclass(frozen=True)
class LinkScope:
    """Codes a model may cite, and what was left out of that permission.

    `excluded` is rows present in the assessment carrying no judgement. It is
    NOT "codes that do not exist" -- those never reach here -- and the copy that
    renders it must not say so, because the two have opposite remedies: a
    misspelling is the model's fault and an unscored control is unfinished
    assessment work.
    """

    codes: frozenset[str]
    total: int

    @property
    def excluded(self) -> int:
        """Rows carrying no judgement.

        `total - len(codes)` is EXACT rather than approximate, and it rests on a
        constraint in another file: all three tables carry
        `UniqueConstraint(assessment_id, <code column>)` and all three code
        columns are `nullable=False`, while every caller filters by a single
        `assessment_id`. So one row yields one distinct non-null code and the
        subtraction counts exactly the unscored rows.

        WHAT WOULD MAKE THIS LIE, stated because the dependency is invisible from
        here: drop either uniqueness constraint, or let a code column go NULL,
        and two rows collapse into one set member -- `excluded` would then report
        rows as unjudged that were judged, understating the scored share in a
        number a client reads. The remedy would be to count judged ROWS
        separately rather than to infer them from the set size.
        """
        return self.total - len(self.codes)


def scope_for(model: type, rows: Sequence[object] | Iterable[object]) -> LinkScope:
    """The `LinkScope` for one assessment's rows.

    Raises `KeyError` on a model with no registered columns rather than
    returning an empty scope. An unknown model is "I could not look", and an
    empty allow-list is a legitimate answer for a scored-nothing assessment --
    so the two must not share a return value. `CLAUDE.md`: a guard that cannot
    read its input must fail closed.
    """
    try:
        code_attr, score_attr = SCORE_COLUMNS[model]
    except KeyError:
        raise KeyError(
            f"{getattr(model, '__name__', model)} has no scored-column pair in "
            "SCORE_COLUMNS; add one rather than defaulting, or the allow-list "
            "silently widens back to every code that exists (#403)."
        ) from None
    codes: set[str] = set()
    total = 0
    for row in rows:
        total += 1
        if getattr(row, score_attr) is not None:
            codes.add(getattr(row, code_attr))
    return LinkScope(codes=frozenset(codes), total=total)


__all__ = ["LinkScope", "SCORE_COLUMNS", "scope_for"]
