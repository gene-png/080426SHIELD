"""The consumer gate must be able to fail, and to refuse to look.

`check_disclosure_consumers` cannot be fixtured by `check_gate_fixtures`'s
harness in the ordinary way -- `run_case` invokes `[sys.executable] + argv` with
a fixture DIRECTORY, and this gate needs a tree shaped like the repo (schemas,
a web surface, exporters). So its both-states evidence lives here, and every
state below was executed rather than reasoned about.

The exit-code split is the point, as everywhere else in this suite. Exit 1 is
"I looked and something is wrong". Exit 2 is "I could not look". They never
share a branch, because `check_audit_evidence`'s `is_code_change([])` printing
"documentation-only change, exempt" and exiting 0 is why that rule exists.
"""

from __future__ import annotations

import pathlib

import pytest
from scripts.check_disclosure_consumers import (
    is_disclosure,
    main,
    repo_root_for,
    unconsumed,
)

pytestmark = pytest.mark.unit


def _tree(
    tmp_path: pathlib.Path, *, schema: str, web: str = "", exporter: str = ""
) -> pathlib.Path:
    """A repo-shaped tree: schemas, a web surface, an exporter."""
    (tmp_path / "apps" / "api" / "app" / "schemas").mkdir(parents=True)
    (tmp_path / "apps" / "api" / "app" / "schemas" / "thing.py").write_text(
        schema, encoding="utf-8"
    )
    # UNDER A SERVICE-NAMED DIRECTORY, matching how this repo organises readers
    # (`components/admin/risk/`, `lib/attack/`, `app/zt/exporters.py`). The
    # gate attributes a reader to a service by its PATH, so a fixture that put
    # every surface at the tree root would be testing a layout the repo does
    # not have -- and would pass for a reason the real tree cannot supply.
    (tmp_path / "apps" / "web" / "src" / "thing").mkdir(parents=True)
    (tmp_path / "apps" / "web" / "src" / "thing" / "Page.tsx").write_text(web, encoding="utf-8")
    if exporter:
        (tmp_path / "apps" / "api" / "app" / "thing").mkdir(parents=True, exist_ok=True)
        (tmp_path / "apps" / "api" / "app" / "thing" / "exporters.py").write_text(
            exporter, encoding="utf-8"
        )
    # Arm 2's structural check: give it a generic renderer so these cases
    # isolate arm 1 rather than tripping on the audit half.
    viewer = tmp_path / "apps" / "web" / "src" / "components" / "admin"
    viewer.mkdir(parents=True)
    (viewer / "AuditViewer.tsx").write_text(
        "const pairs = Object.entries(details);", encoding="utf-8"
    )
    return tmp_path / "apps" / "api" / "app" / "schemas" / "thing.py"


_ALPHA_SCHEMA = """
class AlphaRunAiResponse:
    excluded_inputs: list
"""

_BETA_SCHEMA = """
class BetaRegisterResponse:
    excluded_inputs: list
"""

_SCHEMA = """
class ThingResponse:
    excluded_inputs: list
    id: str
"""


def test_a_disclosure_nobody_renders_is_a_violation(tmp_path, capsys) -> None:
    """THE NEGATIVE CONTROL. Without it this file proves the gate RUNS."""
    seed = _tree(tmp_path, schema=_SCHEMA, web="export const x = 1;")
    assert main(["x", str(seed)]) == 1
    out = capsys.readouterr().out
    assert "excluded_inputs" in out
    assert "The endpoint is not the surface" in out


def test_a_disclosure_rendered_on_a_SCREEN_passes(tmp_path) -> None:
    seed = _tree(tmp_path, schema=_SCHEMA, web="data.excluded_inputs.length;")
    assert main(["x", str(seed)]) == 0


def test_a_disclosure_rendered_only_in_a_DELIVERABLE_passes(tmp_path) -> None:
    """The half a web-only search gets wrong.

    `unusable_target_codes` has no reference under `apps/web/src` and reaches
    the client through `zt/exporters.py`. A gate scoped to the web surface
    reports a defect over a field that already reaches the reader who matters
    most -- and `CLAUDE.md` says "a screen OR a delivered artifact".
    """
    seed = _tree(
        tmp_path,
        schema=_SCHEMA,
        web="export const x = 1;",
        exporter="if gap.excluded_inputs:\n    pass\n",
    )
    assert main(["x", str(seed)]) == 0


def test_a_non_disclosure_field_needs_no_consumer(tmp_path) -> None:
    """A gate demanding a reader for every field fires on ids and cursors and
    is turned off within a week."""
    seed = _tree(
        tmp_path,
        schema="class ThingResponse:\n    id: str\n    created_at: str\n    excluded_inputs: list\n",
        web="data.excluded_inputs;",
    )
    assert main(["x", str(seed)]) == 0


def test_a_request_model_is_not_checked(tmp_path) -> None:
    """Keyed on the `Response` suffix. A request model carries no disclosure
    anyone reads, and checking it would fire on every intake payload."""
    seed = _tree(
        tmp_path,
        schema="class ThingRequest:\n    excluded_inputs: list\n",
        web="export const x = 1;",
    )
    assert main(["x", str(seed)]) == 2  # zero disclosure fields -> could not look


def test_no_repo_above_the_start_is_two_not_zero(tmp_path) -> None:
    assert main(["x", str(tmp_path / "nowhere")]) == 2


def test_an_unparseable_schema_is_two_not_a_silent_skip(tmp_path, capsys) -> None:
    """A schema this gate cannot read is a schema it is not checking."""
    seed = _tree(tmp_path, schema="class ThingResponse:\n    excluded_inputs: (((\n", web="")
    assert main(["x", str(seed)]) == 2
    assert "could not look" in capsys.readouterr().err


def test_a_missing_web_surface_is_two(tmp_path) -> None:
    """The api container mounts only `apps/api`. A verdict from one surface
    would report every web-rendered field as unconsumed."""
    seed = _tree(tmp_path, schema=_SCHEMA, web="data.excluded_inputs;")
    import shutil

    shutil.rmtree(tmp_path / "apps" / "web" / "src")
    assert main(["x", str(seed)]) == 2


def test_zero_disclosure_fields_is_could_not_look(tmp_path, capsys) -> None:
    """The `rglob` hole `check_test_integrity` shipped with: a predicate that
    matches nothing reports clean. Finding none here means the predicate broke."""
    seed = _tree(tmp_path, schema="class ThingResponse:\n    id: str\n", web="")
    assert main(["x", str(seed)]) == 2
    assert "predicate broke" in capsys.readouterr().err


def test_an_unknown_argument_cannot_look(tmp_path) -> None:
    """A flag this script does not implement must not succeed."""
    seed = _tree(tmp_path, schema=_SCHEMA, web="data.excluded_inputs;")
    assert main(["x", str(seed), "--bogus"]) == 2


def test_the_predicate_matches_the_shape_not_a_list() -> None:
    assert is_disclosure("entries_without_tier")
    assert is_disclosure("discarded_entries")
    assert is_disclosure("source_rows_total")
    assert is_disclosure("withheld_count")
    assert not is_disclosure("client_id")
    assert not is_disclosure("created_at")


def test_the_match_is_word_bounded() -> None:
    """A bare substring test would count `excluded_inputs_recorded` as a
    consumer of `excluded_inputs`, which is a different field."""
    # The reader path carries the service token `s`, so these isolate the WORD
    # BOUNDARY rather than the per-service scoping (which has its own test).
    fields = [("s.py", "SResponse", "excluded_inputs")]
    assert unconsumed(fields, [("apps/web/src/s/P.tsx", "excluded_inputs_recorded")]) == fields
    assert unconsumed(fields, [("apps/web/src/s/P.tsx", "data.excluded_inputs")]) == []


def test_the_real_tree_resolves_its_own_root() -> None:
    """`repo_root_for` walks up for a marker rather than counting parents --
    the `parents[N]` shape that cost a pytest session in #314.

    SKIPS IN-CONTAINER, with the condition stated rather than branched on
    silently: the api container mounts `apps/api` at `/app` (#314 again), so
    no `apps/api/app/schemas` exists above this file and the marker cannot be
    found. That is the environment, not the function. CI runs a full checkout,
    which is where this assertion means something -- the same split, and the
    same reason, as the skip in `test_gate_fixtures_harness.py`.
    """
    here = pathlib.Path(__file__).resolve()
    root = repo_root_for(here)
    if root is None:
        pytest.skip(
            "no `apps/api/app/schemas` above this file -- the api container "
            "mounts apps/api at /app (#314). Checked on a full checkout, "
            "which is what CI runs."
        )
    assert (root / "apps" / "api" / "app" / "schemas").is_dir()


@pytest.mark.unit
def test_a_disclosure_read_only_by_ANOTHER_SERVICE_is_a_violation(tmp_path, capsys) -> None:
    """THE REGRESSION TEST for the defect this gate shipped with.

    Field names are not unique across models. `batches_total` is declared on
    BOTH `AttackRunAiResponse` and `RiskRegisterResponse`, and only ATT&CK
    renders it -- so under the original pooled-blob match the Risk field was
    satisfied by ATT&CK's panel and the gate ran GREEN over a live instance of
    the defect it exists to catch. It would have gone red only if someone
    deleted the ATT&CK component.

    This builds that exact shape: one service declares the field and renders
    it, a second declares the same name and renders nothing.
    """
    (tmp_path / "apps" / "api" / "app" / "schemas").mkdir(parents=True)
    (tmp_path / "apps" / "api" / "app" / "schemas" / "alpha.py").write_text(
        _ALPHA_SCHEMA, encoding="utf-8"
    )
    (tmp_path / "apps" / "api" / "app" / "schemas" / "beta.py").write_text(
        _BETA_SCHEMA, encoding="utf-8"
    )
    # ALPHA renders it. BETA does not.
    (tmp_path / "apps" / "web" / "src" / "alpha").mkdir(parents=True)
    (tmp_path / "apps" / "web" / "src" / "alpha" / "Panel.tsx").write_text(
        "const n = data.excluded_inputs.length;", encoding="utf-8"
    )
    (tmp_path / "apps" / "web" / "src" / "beta").mkdir(parents=True)
    (tmp_path / "apps" / "web" / "src" / "beta" / "Panel.tsx").write_text(
        "export const nothing = 1;", encoding="utf-8"
    )
    viewer = tmp_path / "apps" / "web" / "src" / "components" / "admin"
    viewer.mkdir(parents=True)
    (viewer / "AuditViewer.tsx").write_text(
        "const pairs = Object.entries(details);", encoding="utf-8"
    )

    seed = tmp_path / "apps" / "api" / "app" / "schemas" / "alpha.py"
    assert main(["x", str(seed)]) == 1

    err = capsys.readouterr().out
    # BETA is reported and ALPHA is not. Asserting only "exit 1" would pass if
    # the gate had flagged both, which is a different and wrong behaviour.
    assert "beta.py::BetaRegisterResponse.excluded_inputs" in err
    assert "alpha.py::AlphaRunAiResponse.excluded_inputs" not in err


@pytest.mark.unit
def test_an_exemption_is_keyed_on_the_model_not_the_bare_field_name() -> None:
    """One exemption must not silently cover every twin.

    `source_rows_total` is declared on three models, `unusable_target_codes` on
    two, `batches_total` on two. A name-keyed exemption written for one would
    clear all of them -- the unstated-exemption shape, and invisible because
    the gate would simply stop reporting.
    """
    from scripts.check_disclosure_consumers import EXEMPT_FIELDS

    for key in EXEMPT_FIELDS:
        assert "::" in key and "." in key.split("::", 1)[1], (
            f"{key!r} is not a `<origin>::<Model>.<field>` triple. A bare field "
            f"name exempts every model declaring it."
        )
