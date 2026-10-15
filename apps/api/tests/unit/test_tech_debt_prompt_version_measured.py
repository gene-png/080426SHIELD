"""The in-tree Tech Debt prompt version is one whose extractions are measured (for #1058).

`extraction_flags` and the not-in-use contradiction count are measured only for
an extraction whose `llm_calls.prompt_version` is in
`PROMPT_VERSIONS_WITH_CLOSED_SCALES` and `PROMPT_VERSIONS_WITH_PREFIX`. Bumping
`PROMPT_VERSION` without adding the new version to both sets turns both
measurements off for every new extraction, with every other test green: the
list reads "not measured" rather than a count. This guard goes red on that
bump instead (advisor ruling, issue 736 comment 6157889321, item 3).

The older version stays in both sets: lists extracted under v3.2 keep being
measured after the bump (same ruling, item 2). That expectation is a literal
from the ruling, not read from the code.
"""

from __future__ import annotations

import pytest

from app.tech_debt.extract import PROMPT_VERSION, PROMPT_VERSIONS_WITH_CLOSED_SCALES
from app.tech_debt.security_scope import PROMPT_VERSIONS_WITH_PREFIX

pytestmark = pytest.mark.unit


def test_the_in_tree_prompt_version_is_measured_for_extraction_flags() -> None:
    assert PROMPT_VERSION in PROMPT_VERSIONS_WITH_CLOSED_SCALES, (
        f"PROMPT_VERSION {PROMPT_VERSION!r} is not in PROMPT_VERSIONS_WITH_CLOSED_SCALES "
        f"{sorted(PROMPT_VERSIONS_WITH_CLOSED_SCALES)}: new extractions' flags would read "
        "'not measured'"
    )


def test_the_in_tree_prompt_version_is_measured_for_the_not_in_use_prefix() -> None:
    assert PROMPT_VERSION in PROMPT_VERSIONS_WITH_PREFIX, (
        f"PROMPT_VERSION {PROMPT_VERSION!r} is not in PROMPT_VERSIONS_WITH_PREFIX "
        f"{sorted(PROMPT_VERSIONS_WITH_PREFIX)}: new extractions' contradiction count "
        "would read 'not measured'"
    )


@pytest.mark.parametrize(
    "measured",
    [PROMPT_VERSIONS_WITH_CLOSED_SCALES, PROMPT_VERSIONS_WITH_PREFIX],
    ids=["closed_scales", "prefix"],
)
def test_v32_extractions_stay_measured(measured: frozenset[str]) -> None:
    assert "v3.2" in measured
