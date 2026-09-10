"""Every suggestion job's PROMPT must name the key its PARSER requires.

#46. `require_list_at` did `data.get(key, [])`, so a missing key became an empty
list, passed the shape guard, and every consumer then read its own key and got
nothing — zero applied, no error, HTTP 200.

It has shipped once already, recorded in `jobs.py`: the CSF prompt asked for
`{"subcategories": [...]}` while the parser read `{"scores": [...]}`, so LIVE
mode discarded every schema-compliant response while fixture mode passed.

**No fixture can catch this.** All five `_fixture_*` builders construct their
response in Python and always use the correct key, so fixture mode agrees with
the parser by construction. Only `csf_score` had a contract test; `zt_score`,
`mitre_map` and `risk_synthesize` were unguarded.

## Why the expectation is read out of the prompt

`CLAUDE.md`: author fixtures from what the PROMPT says, never from what the
parser expects — a test built on the parser's own constants agrees with it by
construction and cannot express the one failure that matters.

The existing `test_csf_ai_contract.py` is an instance of that flaw: it builds
its "prompt-compliant" response out of `_PARSER_ROW_KEYS`, the parser's
constants. It is left alone here (out of this issue's territory) and its
weakness is why these tests parse the prompt TEXT instead.

So: extract the top-level key from the JSON example the prompt instructs, and
require it to equal the key the job declares. If someone edits a prompt to ask
for a different container, this goes red — which is the drift that shipped.
"""

from __future__ import annotations

import json
import re

import pytest

from app.ai.engine import AIResponseShapeError, get_job, registered_jobs

# The four SUGGESTION jobs. `tech_debt_extract` is excluded deliberately and the
# exclusion is stated rather than implied: its response is consumed by the
# extraction path rather than by a `data[key]` suggestion loop, so it declares
# no top-level list key and there is no contract of this shape to check. If it
# ever gains one, `test_every_declared_key_is_covered` below fails.
SUGGESTION_JOBS = ("csf_score", "zt_score", "mitre_map", "risk_synthesize")


def _prompt_top_level_key(prompt: str) -> str:
    """The top-level key of the first JSON object the PROMPT instructs.

    Deliberately naive: it finds the first `{"<key>":` in the prompt text. The
    prompts all document their contract as a literal JSON example, and reading
    that example is the whole point — anything cleverer would start inferring
    what the prompt meant rather than what it says.
    """
    match = re.search(r'\{\s*"([A-Za-z_][A-Za-z0-9_]*)"\s*:', prompt)
    if match is None:  # pragma: no cover - a prompt with no JSON example
        raise AssertionError(
            "prompt documents no JSON object example, so a model has nothing "
            "to obey and the parser's key cannot be checked against it"
        )
    return match.group(1)


@pytest.mark.unit
@pytest.mark.parametrize("job_name", SUGGESTION_JOBS)
def test_prompt_documents_the_key_the_parser_requires(job_name: str) -> None:
    job = get_job(job_name)
    assert job.top_level_key is not None, (
        f"{job_name} declares no top_level_key, so nothing forces its parser "
        "and its prompt to agree"
    )
    assert _prompt_top_level_key(job.prompt) == job.top_level_key, (
        f"{job_name}: the prompt instructs "
        f'{{"{_prompt_top_level_key(job.prompt)}": ...}} while the parser '
        f'requires "{job.top_level_key}". A model obeying this prompt has '
        "every response discarded, and only a LIVE run would show it."
    )


@pytest.mark.unit
@pytest.mark.parametrize("job_name", SUGGESTION_JOBS)
def test_a_response_with_the_wrong_key_is_REFUSED_not_silently_emptied(
    job_name: str,
) -> None:
    """The #46 mechanism itself, asserted per job.

    Before the fix this returned `{"wrong_key": [...]}` unchanged and the
    caller applied nothing while reporting success.
    """
    job = get_job(job_name)
    with pytest.raises(AIResponseShapeError):
        job.parser(json.dumps({"wrong_key": [{"anything": 1}]}))


@pytest.mark.unit
@pytest.mark.parametrize("job_name", SUGGESTION_JOBS)
def test_an_EMPTY_list_under_the_right_key_is_still_accepted(job_name: str) -> None:
    """The thing the leniency was accidentally protecting, kept on purpose.

    "No suggestions" is a legitimate answer and it is expressible WITH the key:
    `{"scores": []}`. Requiring the key must not turn that into an error, or
    the fix trades a silent zero for a broken valid path — which is the
    over-match failure this repo records.
    """
    job = get_job(job_name)
    assert job.top_level_key is not None
    parsed = job.parser(json.dumps({job.top_level_key: []}))
    assert parsed[job.top_level_key] == []


@pytest.mark.unit
def test_every_declared_key_is_covered_by_this_file() -> None:
    """A new suggestion job must not be able to skip this contract silently.

    Derived from the registry rather than from the list at the top of this
    file: an enumeration that nothing checks is how the first drift survived.
    """
    declared = {name for name in registered_jobs() if get_job(name).top_level_key is not None}
    assert declared == set(SUGGESTION_JOBS), (
        "a job declares a top_level_key but is not covered here (or vice "
        f"versa): registry={sorted(declared)} covered={sorted(SUGGESTION_JOBS)}"
    )
