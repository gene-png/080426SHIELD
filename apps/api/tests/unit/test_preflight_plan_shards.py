"""Preflight keeps ONE local run of the suite when CI deals it across legs.

CI's Python unit suite runs in a `shard`/`of` matrix (`python-shard`) whose
aggregate reads `needs.*` and so stays on GitHub. `preflight_plan.py` plans the
legs here as the one leg of one: `matrix.shard` and `matrix.of` resolve to 1, so
the deal hands that single run EVERYTHING, `if: matrix.shard == 1` steps (the
lint and the gates) run, and the unit step is still found, and narrowed, though
it is now spelled `python -m pytest`. A matrix this does not model stays could-
not-look, never a guessed value.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

# The DOTTED form, deliberately: see test_leave_row_oracle_anchors.py.
import scripts.preflight_plan as pp

pytestmark = pytest.mark.unit

LEGS = """\
on: pull_request
jobs:
  python-shard:
    name: Python (unit shard ${{ matrix.shard }}/${{ matrix.of }})
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        shard: [1, 2]
        of: [2]
    env:
      SHIELD_SHARD_INDEX: ${{ matrix.shard }}
      SHIELD_SHARD_OF: ${{ matrix.of }}
    steps:
      - uses: actions/checkout@v7
      - name: lint
        if: matrix.shard == 1
        run: ruff check .
      - name: gate
        run: python -m scripts.check_ci_selection --selected-out "$RUNNER_TEMP/pytest-selection.txt"
      - name: unit
        run: python -m pytest -m unit tests/unit -n 4 -p scripts.shard_deselect --junitxml="$RUNNER_TEMP/u.xml"
      - name: collect
        run: cp "$RUNNER_TEMP/pytest-dealt.txt" "$RUNNER_TEMP/leg/dealt-$SHIELD_SHARD_INDEX.txt"
      - uses: actions/upload-artifact@v7
        with:
          name: python-shard-${{ matrix.shard }}
          path: ${{ runner.temp }}/leg
  python:
    name: Python (ruff + black + pytest + bandit)
    needs: [python-shard]
    if: always()
    runs-on: ubuntu-latest
    steps:
      - env:
          LEGS: ${{ needs.python-shard.result }}
        run: test "$LEGS" = success
"""


def _plan(tmp_path: Path, text: str, unit: str = "full", narrow: list[str] | None = None):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text(textwrap.dedent(text), encoding="utf-8")
    return pp.plan(tmp_path, "main", "0", unit, narrow or [])


def _by_name(steps: list[dict]) -> dict[str, dict]:
    return {s["name"]: s for s in steps}


def test_the_legs_run_here_as_one_leg_that_is_dealt_everything(tmp_path: Path) -> None:
    steps = _plan(tmp_path, LEGS)
    legs = [s for s in steps if s["job"] == "python-shard"]
    assert [s["name"] for s in legs] == ["lint", "gate", "unit", "collect"]
    assert {s["kind"] for s in legs} == {"run"}, "the leg-1 `if` must not drop the lint here"
    env = "\n".join(legs[2]["env"])
    assert "export SHIELD_SHARD_INDEX=1" in env, env
    assert "export SHIELD_SHARD_OF=1" in env, env
    assert "${{" not in "".join(s["script"] + "".join(s["env"]) for s in legs)


def test_the_aggregate_stays_on_github(tmp_path: Path) -> None:
    kinds = {s["job"]: s["kind"] for s in _plan(tmp_path, LEGS)}
    assert kinds == {"python-shard": "run", "python": "github"}, kinds


def test_the_unit_step_is_found_and_left_alone_in_full_mode(tmp_path: Path) -> None:
    unit = _by_name(_plan(tmp_path, LEGS))["unit"]
    assert unit["script"].strip() == (
        'python -m pytest -m unit tests/unit -n 4 -p scripts.shard_deselect --junitxml="$RUNNER_TEMP/u.xml"'
    )


def test_narrow_keeps_the_command_ci_spells_and_the_plugin(tmp_path: Path) -> None:
    steps = _plan(tmp_path, LEGS, "narrow", ["tests/unit/test_a.py", "tests/unit/test_b.py"])
    legs = [s for s in steps if s["job"] == "python-shard"]
    names = [s["name"] for s in legs]
    gate_at = names.index("gate")
    assert "NARROWED by preflight" in names[gate_at + 1]
    unit = legs[gate_at + 2]
    assert unit["script"].strip() == (
        "python -m pytest -m unit tests/unit/test_a.py tests/unit/test_b.py -n 4 "
        '-p scripts.shard_deselect --junitxml="$RUNNER_TEMP/u.xml"'
    )


def test_the_older_spelling_is_still_the_unit_step(tmp_path: Path) -> None:
    text = LEGS.replace("python -m pytest -m unit", "pytest -m unit")
    unit = _by_name(_plan(tmp_path, text))["unit"]
    assert unit["script"].startswith("pytest -m unit tests/unit -n 4")


def test_a_matrix_with_more_than_shard_and_of_is_not_resolved(tmp_path: Path) -> None:
    text = LEGS.replace("        of: [2]\n", "        of: [2]\n        extra: [a]\n")
    with pytest.raises(pp.CouldNotLook, match="matrix.shard"):
        _plan(tmp_path, text)


def test_a_leg_one_condition_outside_a_shard_matrix_is_not_understood(tmp_path: Path) -> None:
    text = LEGS.replace(
        "    strategy:\n      fail-fast: false\n      matrix:\n        shard: [1, 2]\n        of: [2]\n",
        "",
    )
    with pytest.raises(pp.CouldNotLook):
        _plan(tmp_path, text)


def test_a_different_condition_on_a_shard_matrix_is_still_refused(tmp_path: Path) -> None:
    text = LEGS.replace("if: matrix.shard == 1", "if: matrix.shard == 2")
    with pytest.raises(pp.CouldNotLook, match="an `if:` this planner does not understand"):
        _plan(tmp_path, text)
