"""`llm_calls.redaction_mode` must record what actually happened (#144).

The audit row's stated job is proving the redactor ran. Before 0046 it could not:
with `SHIELD_REDACTION_MODE=off` the redactor returns the input unchanged and
`redacted_counts` stores NULL, byte-identical to a run that executed and found
nothing to remove. `llm_calls.mode` is fixture-vs-live, a different axis.

Two properties, and the second is the one that is easy to lose later:

  1. The mode is recorded, for every mode.
  2. NULL means NOT RECORDED and is never coerced to a default. A pre-0046 row
     has an unknown mode; writing "strict" onto it would fabricate a record in
     the table whose purpose is proving what happened.
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect

from app.models.llm_call import LLMCall


@pytest.mark.unit
def test_the_column_is_nullable_with_no_server_default() -> None:
    """A DB default would manufacture exactly the value 0046 declines to.

    It would also apply to every future writer that forgets to set the field,
    which is the silent half: the row would look recorded and be a guess.
    """
    col = inspect(LLMCall).columns["redaction_mode"]
    assert col.nullable is True
    assert col.server_default is None, (
        "a server default fabricates the mode for pre-0046 rows and for any "
        "writer that forgets to set it"
    )
    assert col.default is None, "a client-side default has the same effect"


@pytest.mark.unit
def test_nothing_updates_the_column_after_insert() -> None:
    """Write-once, unlike `status` / tokens / `duration_ms` on the same row.

    The mode is known before the provider is called and the row is inserted with
    it, so a call that fails or is killed still records what was egressed --
    which is exactly when that matters. A later assignment would mean a failed
    call could carry a mode it never ran under.

    Asserted over the SOURCE because the property is "no code path does this",
    which no single execution can demonstrate.
    """
    from pathlib import Path

    llm_source = (Path(__file__).resolve().parents[2] / "app" / "ai" / "llm.py").read_text(
        encoding="utf-8"
    )
    assignments = [
        line.strip()
        for line in llm_source.split("\n")
        if "redaction_mode" in line and "=" in line and "==" not in line
    ]
    mutations = [
        line
        for line in assignments
        if line.startswith("row.redaction_mode") or line.startswith("call.redaction_mode")
    ]
    assert not mutations, f"redaction_mode is written after insert: {mutations}"


@pytest.mark.unit
def test_the_mode_is_written_at_insert_not_at_finalisation() -> None:
    """`redaction_mode=mode` must appear in the LLMCall(...) constructor call.

    Setting it during finalisation would leave a failed or killed call NULL --
    and the failure path is exactly when "what was egressed" matters most. This
    asserts the property structurally, because a passing happy-path test cannot
    distinguish "written at insert" from "written at finalise".
    """
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "app" / "ai" / "llm.py").read_text(
        encoding="utf-8"
    )
    start = source.index("row = LLMCall(")
    end = source.index("db.add(row)", start)
    constructor = source[start:end]
    # The trailing comma is load-bearing: "redaction_mode=mode" is a PREFIX of
    # "redaction_mode=mode_for_ledger", so without it a writer that records
    # settings instead of the argument the redactor ran under keeps this test
    # green. Verified by mutation on 2026-08-25 -- 20 tests passed against
    # exactly that edit before the comma was added.
    assert "redaction_mode=mode," in constructor, (
        "redaction_mode is not set in the LLMCall constructor from the same "
        "`mode` the redactor ran under -- a call that fails before finalising "
        "would record no mode, and a different variable would record a guess"
    )
    assert "status=LLMCallStatus.RUNNING" in constructor, (
        "the insert no longer looks the way this test assumes; re-check that "
        "redaction_mode is still written before the provider call"
    )


@pytest.mark.unit
def test_only_one_code_path_constructs_an_llm_call() -> None:
    """The NULL-means-pre-0046 invariant rests on there being ONE insert site.

    `test_the_mode_is_written_at_insert_not_at_finalisation` pins that THIS site
    records the mode. Nothing pins that it is the only one -- and a second
    constructor added later, without `redaction_mode=`, would write fresh NULLs
    that are byte-identical to pre-migration rows. NULL would then mean "before
    0046, or written by the other path", and every retrospective question the
    column exists to answer goes ambiguous. The property holds by construction
    today with nothing enforcing it, which is the pairing-kept-in-sync-by-hand
    shape this repo has been bitten by before.

    Asserted over the SOURCE for the same reason as its sibling: "no other code
    path does this" is not demonstrable by executing one path. A `LLMCall(` in a
    comment or a string trips it too -- an over-strict guard here costs one read
    and buys the invariant.

    SCOPE: `apps/api/app` only, and that is the invariant rather than a
    shortcut. The claim is that no PRODUCTION path writes NULL; a constructor in
    `tests/` cannot put a row in a real database, so it is out of scope by
    definition -- `test_admin_audit_viewer.py` and `test_service_stages.py` both
    build one and both are irrelevant here. `scripts/` and `alembic/versions/`
    are NOT irrelevant and are NOT yet covered: a seeder or a backfill
    `UPDATE llm_calls SET redaction_mode=...` would break the invariant and pass
    this test. Stated so the next reader sees a scope decision rather than an
    oversight.
    """
    from pathlib import Path

    app_dir = Path(__file__).resolve().parents[2] / "app"
    sites: list[str] = []
    for path in sorted(app_dir.rglob("*.py")):
        lines = path.read_text(encoding="utf-8").split("\n")
        for lineno, line in enumerate(lines, start=1):
            if "LLMCall(" not in line or line.lstrip().startswith("class LLMCall("):
                continue
            sites.append(f"{path.relative_to(app_dir).as_posix()}:{lineno}")

    assert len(sites) == 1, (
        "llm_calls.redaction_mode's NULL invariant requires exactly one insert "
        f"site under app/; found {len(sites)}: {sites}. A second constructor must set "
        "redaction_mode= at insert, or NULL stops meaning 'pre-0046'."
    )
    assert sites[0].startswith("ai/llm.py:"), (
        f"the sole LLMCall construction moved to {sites[0]}; the redacting "
        "egress client is the only place that knows the mode it ran under"
    )


@pytest.mark.unit
@pytest.mark.parametrize("bogus", ["Strict", "RedactionMode.STRICT", "nonsense", "OFF", ""])
def test_a_value_outside_the_domain_cannot_be_persisted(bogus: str) -> None:
    """On the column whose job is proof, an unproducible value must not land.

    The domain is `RedactionMode` itself via `get_args`, so `app/ai/redact.py`
    stays the single source and a fourth mode is added in one place.

    `validate_strings=True` is what makes this true and is NOT the default --
    measured before the change: a string-member `Enum` binds 'Strict' and
    'nonsense' straight through. This test would pass vacuously against a bare
    `String(16)` if it asserted anything weaker than a raise.
    """
    from sqlalchemy.dialects import postgresql

    col_type = inspect(LLMCall).columns["redaction_mode"].type
    dialect = postgresql.dialect()
    processor = col_type.dialect_impl(dialect).bind_processor(dialect)

    with pytest.raises(LookupError):
        processor(bogus)


@pytest.mark.unit
@pytest.mark.parametrize("mode", ["strict", "standard", "off"])
def test_every_real_mode_and_null_still_bind(mode: str) -> None:
    """The other half: the domain must not have narrowed what is legitimate.

    NULL especially -- it is the pre-0046 record, and a domain that rejected it
    would force the backfill 0046 exists to refuse.
    """
    from sqlalchemy.dialects import postgresql

    col_type = inspect(LLMCall).columns["redaction_mode"].type
    dialect = postgresql.dialect()
    processor = col_type.dialect_impl(dialect).bind_processor(dialect)

    assert processor(mode) == mode
    assert processor(None) is None
