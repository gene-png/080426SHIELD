"""A sixth not-ready branch must not reach a consultant undescribed (#471).

## Why this test exists ON THIS SIDE

`RunAiGuard.tsx` renders `status.detail`, and `RunAiGuard.test.tsx` drives one
case per not-ready branch from a table called `READINESS_BRANCHES`. That table is
LOCAL TO THAT TEST, so its set-level assertions iterate the very list a forgetful
author would have failed to extend: add a sixth branch to `_ai_readiness` and
leave the table at five, and every web assertion stays green.

An earlier version of this branch claimed in a comment that adding a sixth branch
"cannot pass here silently." That was false, and the adversarial reviewer on #471
was right to call it: a test cannot be its own tripwire for a fact that lives in
another language's source file.

**So the tripwire sits where the change ORIGINATES.** `CLAUDE.md`'s
`SCHEMA_REASON_PREFIX` property: a pointer on the CONSUMING side closes nothing,
because the person editing `_ai_readiness` never opens a `.tsx` file. Whoever adds
a branch here gets a red from here, and the failure message names the file they
also have to touch.

## What this does NOT establish, stated so nobody reads more into it

It pins the COUNT, not the text. It cannot tell whether the web table's expected
strings still match what the server sends -- nothing in this repository can,
because the strings are duplicated across a language boundary by hand and there is
no shared artifact to derive them from. Rewording a branch tomorrow reddens
nothing. That residual is real and is written down rather than papered over; the
count is the half that is mechanisable, and it is the half that catches the
forgetful-author case this test is named for.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

#: Every `return (False, ...)` in `_ai_readiness`, one per cause a consultant can
#: be shown. Five as of #471: no key at all; an environment key with the mode not
#: live; a provider with no key-based adapter; the anthropic SDK missing; a model
#: id that is a known placeholder.
#:
#: FOUR OF THE FIVE SAY A KEY IS LOADED, which is why `RunAiGuard` renders
#: `detail` rather than one hardcoded sentence.
EXPECTED_NOT_READY_BRANCHES = 5

#: The web test that must gain a row whenever the number above changes. Named as
#: a string rather than resolved, because `apps/web` is not mounted in the api
#: container and this test must still run there.
WEB_TABLE = "apps/web/src/components/admin/RunAiGuard.test.tsx (READINESS_BRANCHES)"


def _ai_readiness_source() -> str:
    admin = Path(__file__).resolve().parents[2] / "app" / "routes" / "admin.py"
    text = admin.read_text(encoding="utf-8")
    start = text.index("def _ai_readiness")
    # The next top-level `def` or `@router` ends the function. Anchored at column
    # zero so a nested def cannot truncate the region early.
    rest = text[start + 1 :]
    ends = [m.start() for m in re.finditer(r"^(def |@router\.)", rest, re.MULTILINE)]
    return rest[: ends[0]] if ends else rest


@pytest.mark.unit
def test_the_not_ready_branch_count_is_what_the_web_table_covers() -> None:
    """RED when a sixth cause is added, naming the file that must follow.

    The assertion is on a COUNT, and the message is the load-bearing part: a bare
    `assert 6 == 5` tells the author their change broke something, not that a
    consultant will otherwise be shown a warning nobody wrote copy for.
    """
    body = _ai_readiness_source()
    # `return (` followed by `False,` on the next line -- the shape every
    # not-ready branch uses. Counted rather than parsed: a regex over source is
    # enough for a count, and an AST walk would be a second thing to get wrong.
    found = len(re.findall(r"return \(\s*\n\s*False,", body))

    assert found == EXPECTED_NOT_READY_BRANCHES, (
        f"`_ai_readiness` now has {found} not-ready branches, not "
        f"{EXPECTED_NOT_READY_BRANCHES}. Every one of them reaches a consultant "
        f"verbatim through the Run-AI guard (#471), so a new branch needs a row "
        f"in {WEB_TABLE} and the constant here updated in the same commit. "
        f"Without the row, the new cause renders untested and the set-level "
        f"assertions over that table stay green because they iterate the table."
    )


@pytest.mark.unit
def test_the_region_this_reads_is_actually_the_function() -> None:
    """The precondition, because a selector that selects nothing passes.

    If `_ai_readiness_source` returned an empty string -- a renamed function, a
    changed decorator, a moved file -- the count above would be 0 and the test
    would fail LOUDLY, which is the right direction. But if it returned the whole
    FILE it would over-count silently and drift upward as unrelated code lands.
    So both ends of the slice are asserted.
    """
    body = _ai_readiness_source()
    assert body, "the `_ai_readiness` region came back empty"
    assert "No API key is loaded" in body, "the slice does not contain branch 1"
    # FRAGMENTS THAT CANNOT WRAP. The first version of this line looked for
    # "is not a usable model id", which the source splits across an implicit
    # string concatenation (`is not a "` / `"usable model id`), so it could never
    # match and the assertion failed over a slice that was entirely correct.
    # That is the wrapped-quote hazard `CLAUDE.md` records for prose greps,
    # reached through a test rather than a grep.
    assert "usable model id" in body, "the slice stops before the last branch"
    assert "Live AI configured" in body, "the slice stops before the ready return"
    # The next function after it must NOT be inside the slice, or the count is
    # over a larger region than the docstring claims.
    assert "def _anthropic_sdk_importable" not in body, (
        "the slice ran past the end of `_ai_readiness`, so the count above is "
        "over more than one function"
    )
