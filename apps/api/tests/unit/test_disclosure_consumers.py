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
    expired_field_exemptions,
    is_disclosure,
    main,
    model_subject,
    repo_root_for,
    unconsumed,
)

pytestmark = pytest.mark.unit


def _tree(
    tmp_path: pathlib.Path,
    *,
    schema: str,
    web: str = "",
    exporter: str = "",
    audit_renderer: bool = False,
) -> pathlib.Path:
    """A repo-shaped tree: schemas, a web surface, an exporter.

    `audit_renderer` defaults to ABSENT because that is the state of the real
    tree: `AuditViewer.tsx` does not iterate `details` yet, and arm 2 is held
    open by `AUDIT_RENDERER_EXEMPT` until #351 lands. A fixture that supplies
    the renderer while the exemption is set builds a state the repo does not
    have -- and, since the exemption now EXPIRES when the renderer arrives,
    that state is a deliberate red rather than a neutral backdrop.

    When #351 merges and the exemption is deleted, this default flips and the
    arm-2 discriminating case the `DEFERRED` entry says is owed becomes
    writable. Nothing here silently adapts to that; the tests go red and say
    which way.
    """
    (tmp_path / "apps" / "api" / "app" / "schemas").mkdir(parents=True)
    (tmp_path / "apps" / "api" / "app" / "schemas" / "thing.py").write_text(
        schema, encoding="utf-8"
    )
    # UNDER A SERVICE-NAMED DIRECTORY, matching how this repo organises readers
    # (`components/admin/risk/`, `lib/attack/`, `app/zt/exporters.py`). The
    # PATH no longer decides attribution -- a reader must name the model's
    # SUBJECT in its own text (#387) -- but the layout is kept, so these
    # fixtures stay a tree this repo could actually have and a regression to
    # path-token matching would still be exercised against a realistic shape
    # rather than a flat directory that satisfies it trivially.
    (tmp_path / "apps" / "web" / "src" / "thing").mkdir(parents=True)
    (tmp_path / "apps" / "web" / "src" / "thing" / "Page.tsx").write_text(web, encoding="utf-8")
    if exporter:
        (tmp_path / "apps" / "api" / "app" / "thing").mkdir(parents=True, exist_ok=True)
        (tmp_path / "apps" / "api" / "app" / "thing" / "exporters.py").write_text(
            exporter, encoding="utf-8"
        )
    viewer = tmp_path / "apps" / "web" / "src" / "components" / "admin"
    viewer.mkdir(parents=True)
    (viewer / "AuditViewer.tsx").write_text(
        "const pairs = Object.entries(details);" if audit_renderer else "const rows = entries;",
        encoding="utf-8",
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
    """The reader names the model's subject AND the field, in one file."""
    seed = _tree(
        tmp_path,
        schema=_SCHEMA,
        web="const t: Thing = d;\nconst n = t.excluded_inputs.length;",
    )
    assert main(["x", str(seed)]) == 0


def test_a_reader_NAMING_THE_FIELD_BUT_NOT_THE_MODEL_is_not_a_consumer(tmp_path, capsys) -> None:
    """THE ATTRIBUTION, isolated -- and #387's mechanism in one fixture.

    The reader sits in this service's own directory and mentions the field. It
    names no model. Under path-token scoping that passed, and the live instance
    was `clients.py::ZtDashboardResponse.unusable_target_codes` cleared by
    `app/zt/exporters.py` reading the OTHER ZT model's identically-named field
    -- a field that reaches no screen at all.

    Note what this fixture deliberately does NOT do: put the reader in some
    other service's directory. That passes under either rule and would say
    nothing about which one is running.
    """
    seed = _tree(tmp_path, schema=_SCHEMA, web="const n = data.excluded_inputs.length;")
    assert main(["x", str(seed)]) == 1
    assert "thing.py::ThingResponse.excluded_inputs" in capsys.readouterr().out


def test_the_subject_is_the_model_minus_its_Response_suffix() -> None:
    assert model_subject("ZtDashboardResponse") == "ZtDashboard"
    assert model_subject("GapAnalysisResponse") == "GapAnalysis"
    # Not every model ends in `Response`; the transformation must not eat a
    # name it was not given.
    assert model_subject("CapabilityList") == "CapabilityList"


def test_a_disclosure_rendered_only_in_a_DELIVERABLE_passes(tmp_path) -> None:
    """The half a web-only search gets wrong.

    `zt.py::GapAnalysisResponse.unusable_target_codes` has no reference under
    `apps/web/src` and reaches the client through `zt/exporters.py`. A gate
    scoped to the web surface reports a defect over a field that already
    reaches the reader who matters most -- and `CLAUDE.md` says "a screen OR a
    delivered artifact".

    The exporter names the SUBJECT, which is what makes it this model's reader
    rather than a same-service file that happens to contain the string. That
    is not fixture decoration: `app/zt/exporters.py` really does import and
    annotate `GapAnalysis`, and it really does not mention `ZtDashboard`.
    """
    seed = _tree(
        tmp_path,
        schema=_SCHEMA,
        web="export const x = 1;",
        exporter="def caption(t: Thing):\n    if t.excluded_inputs:\n        pass\n",
    )
    assert main(["x", str(seed)]) == 0


def test_a_non_disclosure_field_needs_no_consumer(tmp_path) -> None:
    """A gate demanding a reader for every field fires on ids and cursors and
    is turned off within a week."""
    seed = _tree(
        tmp_path,
        schema="class ThingResponse:\n    id: str\n    created_at: str\n    excluded_inputs: list\n",
        web="const t: Thing = d;\nt.excluded_inputs;",
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


def test_no_repo_above_the_start_is_two_not_zero(tmp_path, capsys) -> None:
    assert main(["x", str(tmp_path / "nowhere")]) == 2
    # The MESSAGE, not just the code. `_contract_failures` demands this of a
    # fixtured gate, and the `DEFERRED` entry standing in for those fixtures
    # claimed every could-not-look case had one while three asserted only the
    # number -- so three exit-2 branches could have been rewired to any other
    # cause, or collapsed into one, with this file green.
    assert "no `apps/api/app/schemas` above" in capsys.readouterr().err


def test_an_unparseable_schema_is_two_not_a_silent_skip(tmp_path, capsys) -> None:
    """A schema this gate cannot read is a schema it is not checking."""
    seed = _tree(tmp_path, schema="class ThingResponse:\n    excluded_inputs: (((\n", web="")
    assert main(["x", str(seed)]) == 2
    assert "could not look" in capsys.readouterr().err


def test_a_missing_web_surface_is_two(tmp_path, capsys) -> None:
    """The api container mounts only `apps/api`. A verdict from one surface
    would report every web-rendered field as unconsumed."""
    seed = _tree(tmp_path, schema=_SCHEMA, web="const t: Thing = d;\nt.excluded_inputs;")
    import shutil

    shutil.rmtree(tmp_path / "apps" / "web" / "src")
    assert main(["x", str(seed)]) == 2
    assert "half the reader surface is unreadable" in capsys.readouterr().err


def test_zero_disclosure_fields_is_could_not_look(tmp_path, capsys) -> None:
    """The `rglob` hole `check_test_integrity` shipped with: a predicate that
    matches nothing reports clean. Finding none here means the predicate broke."""
    seed = _tree(tmp_path, schema="class ThingResponse:\n    id: str\n", web="")
    assert main(["x", str(seed)]) == 2
    assert "predicate broke" in capsys.readouterr().err


def test_a_LEADING_unknown_flag_cannot_look(capsys) -> None:
    """The flag guard, exercised through the slot the guard actually reads.

    This case used to pass the flag in `argv[2]`, behind a path -- which is
    the ARITY branch, three lines further down. The leading-flag guard had
    zero coverage: deleting it left the suite green, and `--bogus` then
    resolved to `<cwd>/--bogus`, whose first PARENT is the repo root, so
    `repo_root_for` rescued the bad argument and the gate ran a normal check
    and exited 0. A guard against a silent success, itself silently unguarded.
    """
    assert main(["x", "--bogus"]) == 2
    assert "is a flag, and this script implements none" in capsys.readouterr().err


def test_a_TRAILING_unknown_argument_cannot_look(tmp_path, capsys) -> None:
    """The other slot, and a different branch: arity, not flag-shape.

    Both are kept because they fail for different reasons and `ci.yml` passes
    a path to three gates -- so for those the first slot is already occupied
    and the trailing one is the live surface (#343).
    """
    seed = _tree(tmp_path, schema=_SCHEMA, web="const t: Thing = d;\nt.excluded_inputs;")
    assert main(["x", str(seed), "--bogus"]) == 2
    assert "too many arguments" in capsys.readouterr().err


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
    # Both readers name the subject `Widget`, so the only thing varying between
    # the two assertions is the field spelling -- the WORD BOUNDARY, not the
    # attribution (which has its own test).
    fields = [("s.py", "WidgetResponse", "excluded_inputs")]
    near = [("apps/web/src/s/P.tsx", "Widget: excluded_inputs_recorded")]
    exact = [("apps/web/src/s/P.tsx", "Widget: data.excluded_inputs")]
    assert unconsumed(fields, near) == fields
    assert unconsumed(fields, exact) == []


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
        "const a: AlphaRunAi = d;\nconst n = a.excluded_inputs.length;", encoding="utf-8"
    )
    (tmp_path / "apps" / "web" / "src" / "beta").mkdir(parents=True)
    (tmp_path / "apps" / "web" / "src" / "beta" / "Panel.tsx").write_text(
        "export const nothing = 1;", encoding="utf-8"
    )
    viewer = tmp_path / "apps" / "web" / "src" / "components" / "admin"
    viewer.mkdir(parents=True)
    # No generic `details` renderer, matching the real tree -- see `_tree`.
    (viewer / "AuditViewer.tsx").write_text("const rows = entries;", encoding="utf-8")

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


@pytest.mark.unit
def test_an_exemption_for_a_field_that_NOW_HAS_A_READER_is_expired() -> None:
    """Somebody did the work and nothing told them to delete the entry.

    Without this the gate is permanently blind to a field it could be
    enforcing, and the reason written on the entry outlives the defect it was
    written about. `check_gate_fixtures`' `DEFERRED` refuses the same state --
    "has fixtures AND is in DEFERRED -- pick one".
    """
    import scripts.check_disclosure_consumers as gate

    key = next(iter(gate.EXEMPT_FIELDS))
    origin, rest = key.split("::", 1)
    model, field = rest.rsplit(".", 1)
    # Every exemption sharing this schema file must be declared, or it is
    # reported as renamed-away and this test reads a verdict about a sibling.
    # `risk.py` holds two, which is how that came up.
    fields = [
        (o, *r.rsplit(".", 1))
        for o, r in (k.split("::", 1) for k in gate.EXEMPT_FIELDS)
        if o == origin
    ]
    # Only this key's own schema file is in scope, so exemptions in OTHER files
    # are not judged here -- the scoping that a test below pins directly.
    origins = {origin}

    # No reader: the exemption is doing its job, and is not reported.
    assert expired_field_exemptions(fields, [("p.tsx", "nothing here")], origins) == []

    # A reader that names this model's subject: the exemption has expired.
    subject = model_subject(model)
    expired = expired_field_exemptions(fields, [("p.tsx", f"{subject}: d.{field}")], origins)
    assert [k for k, _ in expired] == [key]
    assert "delete the exemption" in expired[0][1]


@pytest.mark.unit
def test_an_exemption_whose_FIELD_WAS_RENAMED_is_expired() -> None:
    """The other expiry: the schema file is there and the field is not.

    The entry then exempts nothing, and the next field to land under that
    triple inherits a reason written about a different defect entirely.
    """
    import scripts.check_disclosure_consumers as gate

    key = next(iter(gate.EXEMPT_FIELDS))
    origin = key.split("::", 1)[0]
    expired = expired_field_exemptions(
        [(origin, "SomethingElseResponse", "dropped_x")], [], {origin}
    )
    assert key in [k for k, _ in expired]
    assert any("the exemption is stale" in why for _, why in expired)


@pytest.mark.unit
def test_an_exemption_is_NOT_judged_against_a_tree_that_lacks_its_schema() -> None:
    """The scoping, pinned -- because its absence produced a confident lie.

    Without it, every one of this suite's fixture trees reported all three real
    exemptions as stale, because a fixture tree has no `risk.py`. The verdict
    read "the exemption is stale" and meant "you are looking at a different
    repository", and eight tests went red at once for a reason none of them
    named.
    """
    assert (
        expired_field_exemptions([("thing.py", "ThingResponse", "dropped_x")], [], {"thing.py"})
        == []
    )


@pytest.mark.unit
def test_the_clean_line_counts_only_the_tree_it_LOOKED_AT(tmp_path, capsys) -> None:
    """The summary arithmetic, pinned -- because nothing here could see it.

    Every other test asserts an exit code, and a nonsense count does not change
    one. The line printed `-2 of 1 disclosure fields` on a fixture tree,
    because it subtracted the GLOBAL exemption count from the fields present:
    the same scope error `expired_field_exemptions` had, surviving in the
    sentence a human reads. It was caught by reading a red-on-revert run's
    output, which is luck rather than coverage.

    Also asserts the exempt fields are NAMED. "all reachable ... (3 exempt
    with reasons)" stated a clean verdict and then parenthesised the fields it
    was not a verdict about -- the `EXEMPT_FIELDS` header's own defect in the
    one line most readers see.
    """
    seed = _tree(tmp_path, schema=_SCHEMA, web="const t: Thing = d;\nt.excluded_inputs;")
    assert main(["x", str(seed)]) == 0
    line = capsys.readouterr().out
    assert "1 of 1 disclosure fields reach a screen or a deliverable" in line
    # No exemption applies to this tree, so none is named.
    assert "exempt with a tracked reason" not in line


@pytest.mark.unit
def test_no_model_subject_is_a_substring_of_another() -> None:
    """The one way the subject attribution can still clear the wrong model.

    The subject is matched as a plain SUBSTRING, and it has to be: the readers
    say `TechDebtDashboardData` and `AttackRunAiResponse`, so a word boundary
    would reject every real one. That leaves one hole -- if one subject were
    contained in another, the containing model's reader would satisfy the
    contained model, which is the cross-model false pass of #387 one level up.

    LATENT, not live, and this is what keeps it that way. Derived from the real
    schemas rather than asserted against the list measured today, so a model
    that lands and breaks it goes red here instead of passing under a sentence
    that used to be true.
    """
    import scripts.check_disclosure_consumers as gate

    root = repo_root_for(pathlib.Path(gate.__file__).resolve())
    if root is None:
        pytest.skip(
            "no repo root above the gate -- the api container mounts apps/api at /app (#314)."
        )
    fields, problems = gate.response_disclosure_fields(root / "apps" / "api" / "app" / "schemas")
    assert not problems, problems
    subjects = sorted({model_subject(m) for _, m, _ in fields})
    contained = [(a, b) for a in subjects for b in subjects if a != b and a in b]
    assert not contained, (
        f"these model subjects contain one another: {contained}. The reader of "
        f"the longer one satisfies the shorter one's fields, so a disclosure "
        f"that reaches nobody would pass. Disambiguate the model names, or "
        f"replace the substring match with something that can tell them apart."
    )


@pytest.mark.unit
def test_every_exemption_names_a_field_that_EXISTS(tmp_path) -> None:
    """The residual `expired_field_exemptions` cannot cover, asserted where it can be.

    An exemption naming a schema file that was DELETED outright is invisible to
    that function by construction -- from inside it, a missing `risk.py` is
    indistinguishable from a fixture tree. This asks the same question of the
    REAL tree, where it is answerable.

    SKIPS IN-CONTAINER for the same stated reason as
    `test_the_real_tree_resolves_its_own_root`: the api container mounts
    `apps/api` at `/app` (#314), so there is no repo root to find. CI runs a
    full checkout, which is where this means something.
    """
    import scripts.check_disclosure_consumers as gate

    root = repo_root_for(pathlib.Path(gate.__file__).resolve())
    if root is None:
        pytest.skip(
            "no `apps/api/app/schemas` above the gate -- the api container "
            "mounts apps/api at /app (#314). Checked on a full checkout."
        )
    fields, problems = gate.response_disclosure_fields(root / "apps" / "api" / "app" / "schemas")
    assert not problems, problems
    declared = {f"{o}::{m}.{f}" for o, m, f in fields}
    for key in gate.EXEMPT_FIELDS:
        assert key in declared, (
            f"{key!r} is exempt and is declared on no `*Response` model in this "
            f"repo. The exemption stands for nothing and will silently cover "
            f"the next field to arrive under that triple."
        )


@pytest.mark.unit
def test_the_audit_renderer_exemption_expires_when_the_renderer_ARRIVES(
    tmp_path, capsys, monkeypatch
) -> None:
    """Arm 2's exemption could be discharged and never read again.

    `AUDIT_RENDERER_EXEMPT` is consulted only on the runs where arm 2 FAILS.
    Once #351's generic `details` renderer exists, the branch holding the
    exemption becomes unreachable -- so the string sits in the file forever,
    and arm 2 can no longer go red if the renderer is later deleted, because
    this exemption would catch it. A deferral that cannot detect its own
    discharge is a permanent exemption wearing an expiry date.
    """
    import scripts.check_disclosure_consumers as gate

    assert gate.AUDIT_RENDERER_EXEMPT is not None, (
        "this test is about the exemption being SET. When #351 lands and the "
        "exemption is deleted, replace it with the case that proves arm 2 "
        "discriminates -- the one the DEFERRED entry says is owed."
    )
    seed = _tree(
        tmp_path,
        schema=_SCHEMA,
        web="const t: Thing = d;\nt.excluded_inputs;",
        audit_renderer=True,
    )
    assert main(["x", str(seed)]) == 1
    assert "EXPIRED exemption" in capsys.readouterr().out

    # And with the exemption cleared, the same tree passes -- so the red above
    # is the EXEMPTION being stale, not the renderer check being broken.
    monkeypatch.setattr(gate, "AUDIT_RENDERER_EXEMPT", None)
    assert main(["x", str(seed)]) == 0
