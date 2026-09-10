"""Every enum-valued field a PROMPT instructs must name tokens the PARSER accepts.

#121. `_RISK_SYNTHESIZE_PROMPT` instructed `likelihood (Very Low..Very High)`
and `impact (Negligible..Catastrophic)`, while `routes/risk.py` parses them
with `enum_cls(value)` — a StrEnum lookup that is case- and separator-exact
against `very_low` … `catastrophic`.

So a model that OBEYS the prompt produces `likelihood=None, impact=None`, and
because tier is derived from the pair, `tier=None` too. The entry is persisted
anyway: `raw["title"]` is the only requirement. The client is then shown
"Open risks 40 · Critical 0 · High 0 · Medium 0", an empty 5×5 matrix, and
forty rows of em dashes — at HTTP 201, with `batches_failed: 0` and no counter
anywhere non-zero.

## This is the sibling of `test_ai_prompt_parser_contract.py`, one level down

That file checks the CONTAINER: the top-level key a prompt asks for must be the
key the parser reads (#46). This one checks the VALUES inside it. Same drift,
same invisibility, same reason no fixture can catch it.

## Why no fixture can catch it, and why CI is green over it permanently

`_fixture_risk_synthesize` cycles `("low", "medium", "high", …)` — the PARSER's
tokens, not the prompt's. Every `_fixture_*` builder constructs its response in
Python and therefore agrees with the parser by construction. Fixture mode
cannot reach this defect, so no e2e will ever fail on it, and `CLAUDE.md`
already lists the Risk Register enum mismatch as a prior instance of the rule
it breaks: author fixtures from what the PROMPT says, never from what the
parser expects.

## Why the expectation is read out of the prompt TEXT

A test that asserted "the prompt contains the enum's members" would be reading
its expectation from the parser's own constants and would agree with them by
construction — the exact flaw `test_csf_ai_contract.py` has and the reason
these contract tests parse prose instead.

So the direction here is: extract the tokens the PROMPT OFFERS a model, and put
each one through the enum the ROUTE actually validates with. A token the prompt
instructs and the parser rejects is the defect, stated as the empirical table
in #121. Nothing is asserted about tokens the prompt does not mention.

## The second half is the one that was actually missing

Requiring every OFFERED token to parse is not enough on its own: a prompt that
offers no tokens at all passes it vacuously, and that is precisely what
`likelihood` and `impact` did — `"likelihood": "..."` in the JSON example, with
only a Title-Case prose range to go on. So a field must also OFFER something. A
model cannot copy a token it was never shown.
"""

from __future__ import annotations

import re

import pytest

from app.ai.engine import get_job
from app.risk.engine import Impact, Likelihood, RecommendedAction, RiskAxis

# The enum-valued fields, and the enum each one is parsed with.
#
# Derived by reading the `_enum_or_none(...)` call sites in `routes/risk.py`
# and the `status` handling in `routes/attack.py` — i.e. from what the code
# actually validates, not from what any prompt happens to say. That direction
# is deliberate: the PARSER decides which fields are enum-valued, and the
# PROMPT is then held to it. Reading the field list out of the prompt would let
# a prompt that forgot a field pass by forgetting it.
ENUM_FIELDS: dict[str, dict[str, type]] = {
    "risk_synthesize": {
        "likelihood": Likelihood,
        "impact": Impact,
        "axis": RiskAxis,
        "recommended_action": RecommendedAction,
    },
}

_CASES = [
    (job, field, enum_cls)
    for job, fields in ENUM_FIELDS.items()
    for field, enum_cls in fields.items()
]


def _tokens_offered(prompt: str, field: str) -> list[str]:
    """Every token the PROMPT offers a model for `field`.

    Two forms, because the prompts use both:

    * the JSON example — `"axis": "detection|prevention|response"`;
    * a prose parenthetical — `a recommended action (remediate, mitigate, …)`.

    A placeholder value (`"..."`) offers nothing and is reported as nothing,
    which is the point: see the module docstring's second half.

    Deliberately literal. Anything cleverer would start inferring what the
    prompt MEANT, and what it means is exactly what is in dispute — a model
    reads the characters.
    """
    tokens: list[str] = []

    # 1. The JSON example: "field": "a|b|c"
    for match in re.finditer(
        rf'"{re.escape(field)}"\s*:\s*"([^"]*)"',
        prompt,
    ):
        value = match.group(1)
        if "|" in value:
            tokens.extend(part.strip() for part in value.split("|") if part.strip())

    # 2. A prose parenthetical following the field name, e.g.
    #    "a recommended action (remediate, mitigate, accept, transfer, avoid)".
    #    Ranges written with "..", such as "(Very Low..Very High)", contribute
    #    their ENDPOINTS: those are the two tokens the prose literally shows,
    #    and a model copying the prompt copies them.
    for match in re.finditer(
        rf"{re.escape(field.replace('_', ' '))}\s*\(([^)]*)\)",
        prompt,
        re.IGNORECASE,
    ):
        inner = match.group(1)
        if ".." in inner:
            tokens.extend(part.strip() for part in inner.split("..") if part.strip())
        else:
            for part in inner.split(","):
                part = part.strip()
                # Prose lists their last item as "or response" / "and avoid".
                # That conjunction is English, not part of the token a model
                # would copy into JSON -- the JSON example beside it shows the
                # bare word. Stripping it is reading the prompt correctly, not
                # being lenient about it.
                part = re.sub(r"^(?:or|and)\s+", "", part, flags=re.IGNORECASE)
                if part:
                    tokens.append(part)

    # Order-preserving dedupe, so a token shown in both forms is reported once.
    seen: set[str] = set()
    return [t for t in tokens if not (t in seen or seen.add(t))]


@pytest.mark.unit
@pytest.mark.parametrize("job_name, field, enum_cls", _CASES)
def test_prompt_offers_at_least_one_token_for_every_enum_field(
    job_name: str, field: str, enum_cls: type
) -> None:
    """A model cannot copy a token it was never shown.

    This is the half that `likelihood` and `impact` failed: the JSON example
    gave them `"..."` and the prose gave a Title-Case range, so the prompt
    named no token the parser would accept — and a per-token check alone would
    have passed vacuously over it.
    """
    prompt = get_job(job_name).prompt
    offered = _tokens_offered(prompt, field)
    assert offered, (
        f'{job_name}: the prompt names no token for the enum field "{field}", '
        f"so a model has nothing to copy and every value it invents is "
        f"rejected silently. Put the accepted tokens in the JSON example, the "
        f'way "axis" already does.'
    )


@pytest.mark.unit
@pytest.mark.parametrize("job_name, field, enum_cls", _CASES)
def test_every_token_the_prompt_offers_is_accepted_by_the_parser(
    job_name: str, field: str, enum_cls: type
) -> None:
    """The #121 table, as an assertion.

    `likelihood 'Very High' -> None` was the shipped behaviour. A token the
    prompt instructs and the parser drops is a silent zero, not an error.
    """
    prompt = get_job(job_name).prompt
    offered = _tokens_offered(prompt, field)
    rejected = []
    for token in offered:
        try:
            enum_cls(token)
        except (ValueError, KeyError):
            rejected.append(token)
    assert not rejected, (
        f"{job_name}.{field}: the prompt instructs {rejected!r}, and "
        f"{enum_cls.__name__} rejects them. A model that OBEYS the prompt "
        f"produces null for this field, the entry is stored anyway, and "
        f"nothing counts it. Accepted: {[m.value for m in enum_cls]!r}"
    )


@pytest.mark.unit
def test_the_field_list_still_matches_the_route() -> None:
    """`ENUM_FIELDS` is hand-derived, so it can go stale silently.

    It is a list, and this repo has a standing rule against those: a list is a
    sample, and the fields it omits are exactly the ones that drift unnoticed.
    Deriving the set from source is not available here without importing the
    route module's internals, so the next best thing is to fail loudly when the
    number of `_enum_or_none` call sites stops matching what is covered.

    Read as a SHAPE rather than a symbol: it counts the call sites in the file
    rather than naming them, so renaming a variable does not break it and
    ADDING a fifth enum field does.
    """
    import pathlib

    route = pathlib.Path(__file__).resolve().parents[2] / "app" / "routes" / "risk.py"
    source = route.read_text(encoding="utf-8")
    call_sites = len(re.findall(r"_coerce_enum\(", source))
    # One definition plus one call per validated field.
    covered = len(ENUM_FIELDS["risk_synthesize"])
    assert call_sites == covered + 1, (
        f"risk.py has {call_sites} `_coerce_enum` occurrences (1 definition + "
        f"{call_sites - 1} call sites) but this file covers {covered} fields. "
        f"An enum field was added or removed and the contract did not follow."
    )
