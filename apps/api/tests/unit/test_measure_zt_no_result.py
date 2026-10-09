"""The consistency measure under the approved ZT prompt (#806, C2 and C3).

`zt_no_result_count` counts the capabilities a run asked about that no entry
named; the expected value is the number of codes each test leaves out. The C2
caveat is stated in the report, because a v2 gap count rests on the engagement
stage and a v1 one on the model's own targets.
"""

from __future__ import annotations

import pytest
from scripts.measure_ai_consistency import ZT_DOWNSTREAM_TARGET_BASIS, zt_no_result_count

from tests.unit.test_measure_ai_consistency import _zt_assessment, world  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit

_ASKED = ["CISA.ID.01", "CISA.ID.02", "CISA.ID.03", "CISA.DV.01"]


@pytest.mark.parametrize(
    "left_out", [set(), {"CISA.ID.02"}, {"CISA.ID.01", "CISA.DV.01"}, set(_ASKED)]
)
def test_no_result_counts_the_codes_no_entry_named(left_out: set[str]) -> None:
    data = {"capabilities": [{"code": c, "current": 1} for c in _ASKED if c not in left_out]}
    assert zt_no_result_count({"capabilities": _ASKED}, data) == len(left_out)


def test_a_refused_entry_still_names_its_code() -> None:
    data = {"capabilities": [{"code": c, "current": 9} for c in _ASKED]}
    assert zt_no_result_count({"capabilities": _ASKED}, data) == 0


def test_the_report_states_what_the_gap_count_is_measured_against() -> None:
    assert "engagement stage" in ZT_DOWNSTREAM_TARGET_BASIS
    assert "not comparable" in ZT_DOWNSTREAM_TARGET_BASIS


def test_zt_measures_and_applies_current_only() -> None:
    """#806 (ruling in #736 comment 6072976838): `current` is the one zt field.
    Pinned to a literal, so a `target` that comes back is noticed."""
    from scripts.measure_ai_consistency import _job_shape

    # test-integrity: the constant IS the subject, pinned to a literal from the ruling
    from app.routes.zt import _ZT_ROW_FIELDS

    assert _ZT_ROW_FIELDS == ("current",)
    assert _job_shape("zt_score")[2] == ("current",)


def test_a_stray_target_in_a_measured_response_is_counted_not_compared() -> None:
    from scripts.measure_ai_consistency import ZtScope, compare_pair

    scope = ZtScope(max_stage=4, codes=frozenset({"C1", "C2"}))
    a = {"capabilities": [{"code": "C1", "current": 2, "target": 3}, {"code": "C2", "current": 1}]}
    b = {"capabilities": [{"code": "C1", "current": 2, "target": 4}, {"code": "C2", "current": 1}]}
    r = compare_pair("zt_score", a, b, context=scope)
    # Counted: one stray key per run, the row in each that carries it.
    assert r["unknown_fields"] == {"a": 1, "b": 1}
    # Not compared: no field for it, and the two runs' different targets
    # leave `current`'s agreement untouched.
    assert "target" not in r["fields"]
    assert (r["fields"]["current"]["compared"], r["fields"]["current"]["equal"]) == (2, 2)


def test_the_console_table_prints_stray_keys_not_unusable_targets(
    world, capsys  # noqa: F811
) -> None:
    """#981 review: with `zt_downstream` reading `current` only, "unusable
    targets" would always print 0 and read as a measurement. Through
    `measure_zt`, a model that sends a `target` on its one row in each of two
    runs prints that count per run instead."""
    from scripts.measure_ai_consistency import _print_table, measure_zt

    from app.ai.llm import LLMClient, LLMResponse

    c, TestSession, provider = world
    code = _zt_assessment(c)
    provider.register_static(
        "zt_score",
        LLMResponse('{"capabilities": [{"code": "' + code + '", "current": 2, "target": 3}]}'),
    )
    with TestSession() as db:
        report = measure_zt(db, LLMClient(provider), framework="cisa", runs=2)
        db.commit()
    capsys.readouterr()

    _print_table(report)

    out = capsys.readouterr().out
    for run in (1, 2):
        assert f"run {run}: client-visible gaps" in out, out
    assert out.count("stray keys such as target (not applied, not measured) 1") == 2, out
    assert "unusable targets" not in out, out
