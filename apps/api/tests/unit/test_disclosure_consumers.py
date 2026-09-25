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
    web_test: str = "",
    web_spec: str = "",
    exporter: str = "",
    audit_renderer: bool = True,
) -> pathlib.Path:
    """A repo-shaped tree: schemas, a web surface, an exporter.

    `audit_renderer` defaults to PRESENT, because that is now the state of the
    real tree: this PR added the generic `details` renderer to
    `AuditViewer.tsx` and deleted `AUDIT_RENDERER_EXEMPT`. A fixture without it
    would build a tree the repo does not have, and every arm-1 test would fail
    on arm 2 for reasons that have nothing to do with what it is testing.

    The default was ABSENT while the exemption was set, for the same reason
    pointed the other way. It flipped here rather than silently adapting: four
    arm-1 tests went red the moment the exemption was deleted, which is what
    told us they had been passing only because arm 2 was suppressed.
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
    # `LatestPanel.tsx`, not `Page.tsx`, and the name is load-bearing: it
    # CONTAINS the substring "test". A naive `if "test" in path.name` filter
    # -- the obvious wrong way to write the exclusion below -- would eat this
    # production file, and with a neutral name no test in this file would say
    # so. "latest" is the realistic instance of the word this class swallows.
    (tmp_path / "apps" / "web" / "src" / "thing" / "LatestPanel.tsx").write_text(
        web, encoding="utf-8"
    )
    if web_test:
        (tmp_path / "apps" / "web" / "src" / "thing" / "LatestPanel.test.tsx").write_text(
            web_test, encoding="utf-8"
        )
    if web_spec:
        # `.spec.` is the OTHER member of TEST_FILE_MARKERS, and it had no
        # fixture at all until the sixth review pass: a filter implementing
        # only `.test.` passed the whole suite. Two markers, one exercised, is
        # the half-sweep shape this repo keeps recording.
        (tmp_path / "apps" / "web" / "src" / "thing" / "InspectorPanel.spec.tsx").write_text(
            web_spec, encoding="utf-8"
        )
    if exporter:
        (tmp_path / "apps" / "api" / "app" / "thing").mkdir(parents=True, exist_ok=True)
        (tmp_path / "apps" / "api" / "app" / "thing" / "exporters.py").write_text(
            exporter, encoding="utf-8"
        )
    viewer = tmp_path / "apps" / "web" / "src" / "components" / "admin"
    viewer.mkdir(parents=True)
    # BOTH halves, because arm 2 needs both. Iteration alone is satisfied by a
    # renderer that EXISTS and is never called -- the "function with no
    # callers" shape -- so the gate also requires a column cell referencing the
    # payload. A fixture emitting only the iteration would build a tree the
    # gate correctly rejects, and every test using it would be about that
    # rejection rather than about its own subject.
    (viewer / "AuditViewer.tsx").write_text(
        (
            "const pairs = Object.entries(details);\ncell: (e) => renderDetails(e.details),"
            if audit_renderer
            else "const rows = entries;"
        ),
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


def test_a_TEST_FILE_is_not_a_reader(tmp_path) -> None:
    """A fixture asserting a field exists does not mean anyone can see it.

    `reader_text` globbed every `.ts`/`.tsx` under `apps/web/src`, so a test
    file naming the field satisfied "reaches a screen" -- and the fixture is
    the first thing a PR adding a disclosure field writes. The gate would have
    reported the field consumed on the strength of the test asserting it is
    not.

    MEASURED on #387's branch before the exclusion, deleting the field name in
    stages and running the gate after each, each deletion asserted to land:
    removing it from `lib/dashboards/zt.ts` left `25 of 25, exit 0`; removing
    it from the two ZT test files as well turned it red. Production code was
    not what cleared it.

    LATENT rather than live when found -- no field in the tree was cleared
    ONLY by a test file, so the exclusion changed no verdict on the day it
    landed. That is why it needs a test: nothing else would notice it being
    undone.
    """
    seed = _tree(
        tmp_path,
        schema=_SCHEMA,
        # The PRODUCTION surface does not mention the field at all.
        web="export const unrelated = 1;",
        # The TEST file names both the subject and the field, which is exactly
        # what `readers_for` requires of a genuine reader.
        web_test="const t: Thing = d;\nexpect(t.excluded_inputs).toEqual([]);",
    )
    assert main(["x", str(seed)]) == 1


def test_a_SPEC_FILE_is_not_a_reader_either(tmp_path) -> None:
    """The other member of `TEST_FILE_MARKERS`, which had no case at all.

    Added by the sixth review pass. `.test.` had a fixture and `.spec.`
    did not, so a filter implementing only `.test.` passed this entire
    suite -- two markers, one exercised. This repo's own half-sweep
    shape, inside the tests written to close a half-sweep.

    The production file names the field nowhere, so only the exclusion
    can decide the verdict.
    """
    seed = _tree(
        tmp_path,
        schema=_SCHEMA,
        web="export const unrelated = 1;",
        web_spec="const t: Thing = d;\nexpect(t.excluded_inputs).toEqual([]);",
    )
    assert main(["x", str(seed)]) == 1


def test_a_PRODUCTION_file_beside_a_test_file_still_passes(tmp_path) -> None:
    """The other half, so the exclusion is a filter and not a blanket refusal.

    Without this, an exclusion that dropped the whole directory -- or every
    file whose name merely contains `test` -- would pass the case above while
    breaking every real reader that happens to sit beside a spec.

    The second half is why `_tree` names the production file `LatestPanel.tsx`.
    It first wrote `Page.tsx`, which contains neither `test` nor `spec`, so a
    naive `"test" in path.name` filter dropped only the test file and this case
    still passed -- the docstring claimed a class the fixture could not reach.
    """
    seed = _tree(
        tmp_path,
        schema=_SCHEMA,
        web="const t: Thing = d;\nt.excluded_inputs;",
        web_test="const t: Thing = d;\nexpect(t.excluded_inputs).toEqual([]);",
    )
    assert main(["x", str(seed)]) == 0


def test_main_PASSES_THE_LIVE_DICT_to_the_expiry_check(tmp_path, monkeypatch, capsys) -> None:
    """The WIRING, which the two expiry tests above cannot see.

    They call `expired_field_exemptions` directly, so they prove the rule
    works given an exemption -- not that `main` ever hands it the real one.
    Change the call site to `exemptions={}` and both stay green while the arm
    is dead in production. That is `CLAUDE.md`'s "the test imports the thing
    it is defending rather than calling the endpoint that reaches it", and it
    is PRE-EXISTING: the older `next(iter(EXEMPT_FIELDS))` tests called the
    function directly too. Found by the #387 review, closed here.

    Monkeypatching the module dict rather than passing an argument is the
    point: the only way this can pass is if `main` reads that dict.
    """
    seed = _tree(
        tmp_path,
        schema=_SCHEMA,
        # A reader exists, so the field is NOT unconsumed and arm 1 is silent.
        # The only thing that can fail this run is the expiry check.
        web="const t: Thing = d;\nt.excluded_inputs;",
    )
    import scripts.check_disclosure_consumers as gate

    # An exemption for a field that HAS a reader -- expired by definition.
    monkeypatch.setitem(
        gate.EXEMPT_FIELDS, "thing.py::ThingResponse.excluded_inputs", "a synthetic reason"
    )
    assert main(["x", str(seed)]) == 1
    # The MESSAGE as well as the code, because `main` has other ways to reach
    # exit 1 and this test's name claims a specific one. The sibling
    # could-not-look cases argue the same thing in their own comments: an exit
    # code alone lets a branch be rewired to any other cause with the file
    # green.
    assert "EXPIRED exemptions" in capsys.readouterr().out


def test_main_is_GREEN_on_the_same_tree_with_no_exemption(tmp_path) -> None:
    """The control, so the case above fails for the expiry and not the tree.

    Without it, any defect in the fixture -- a missing audit renderer, an
    unreadable schema -- produces the same exit 1 and the test still "passes".
    """
    seed = _tree(
        tmp_path,
        schema=_SCHEMA,
        web="const t: Thing = d;\nt.excluded_inputs;",
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
    # A SYNTHETIC exemption, not `next(iter(gate.EXEMPT_FIELDS))`.
    #
    # Drawing a live key made this test a hostage to the dict's CONTENTS: the
    # two arms below are about the expiry RULE, and they went from green to
    # `StopIteration` the moment #387 discharged the last real entry and left
    # `EXEMPT_FIELDS` empty -- a test of a rule, broken by data the rule is
    # not about. Guarding with a skip-when-empty would be worse: the arm would
    # then be pinned by nothing on the very tree where the dict is empty,
    # which is this one.
    #
    # `CLAUDE.md`: derive the world the test needs; never let the setup depend
    # on the thing under test happening to be in some state.
    #
    # The origin is a SCHEMA FILENAME (`clients.py`), which is the shape every
    # real key and `main`'s own `origins` set use. It first read
    # `app/zt/exporters.py` -- a PATH, and a key shape nothing can produce.
    # Inert, because this function only splits on `::` and tests set
    # membership; corrected anyway, in the file that had just fixed a fixture
    # for building an unreachable state.
    key = "clients.py::SyntheticExemptResponse.dropped_synthetic"
    origin, rest = key.split("::", 1)
    model, field = rest.rsplit(".", 1)
    # Every exemption sharing this schema file must be declared, or it is
    # reported as renamed-away and this test reads a verdict about a sibling.
    # `risk.py` holds two, which is how that came up.
    fields = [(origin, model, field)]
    # Only this key's own schema file is in scope, so exemptions in OTHER files
    # are not judged here -- the scoping that a test below pins directly.
    origins = {origin}

    synthetic = {key: "a synthetic reason"}

    # No reader: the exemption is doing its job, and is not reported.
    assert (
        expired_field_exemptions(fields, [("p.tsx", "nothing here")], origins, exemptions=synthetic)
        == []
    )

    # A reader that names this model's subject: the exemption has expired.
    subject = model_subject(model)
    expired = expired_field_exemptions(
        fields, [("p.tsx", f"{subject}: d.{field}")], origins, exemptions=synthetic
    )
    assert [k for k, _ in expired] == [key]
    assert "delete the exemption" in expired[0][1]


@pytest.mark.unit
def test_an_exemption_whose_FIELD_WAS_RENAMED_is_expired() -> None:
    """The other expiry: the schema file is there and the field is not.

    The entry then exempts nothing, and the next field to land under that
    triple inherits a reason written about a different defect entirely.
    """
    # Synthetic, for the reason given in the test above.
    key = "clients.py::SyntheticExemptResponse.dropped_synthetic"
    origin = key.split("::", 1)[0]
    expired = expired_field_exemptions(
        [(origin, "SomethingElseResponse", "dropped_x")],
        [],
        {origin},
        exemptions={key: "a synthetic reason"},
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
def test_the_audit_renderer_exemption_is_DISCHARGED_and_the_slot_still_works(
    tmp_path, capsys, monkeypatch
) -> None:
    """The exemption is `None`, and setting one again still suppresses arm 2.

    This replaces the expiry test, which asserted the exemption was SET and
    told whoever deleted it to write this. Its reasoning holds and is why the
    slot is kept rather than removed: while a string is set, arm 2 cannot go
    red, so the renderer could be deleted and nothing would say so.

    Both halves, because a slot observed in one state is not observed.
    """
    import scripts.check_disclosure_consumers as gate

    assert gate.AUDIT_RENDERER_EXEMPT is None, (
        "the exemption is discharged; #351 shipped the renderer. If it is set "
        "again, arm 2 is suppressed and cannot notice the renderer going away."
    )

    # Arm 2 red, for real, with no exemption to catch it.
    missing = _tree(
        tmp_path / "a",
        schema=_SCHEMA,
        web="const t: Thing = d;\nt.excluded_inputs;",
        audit_renderer=False,
    )
    assert main(["x", str(missing)]) == 1
    assert "nothing renders the audit `details` payload generically" in capsys.readouterr().out

    # The same tree passes once a string is set -- so the slot still
    # suppresses, and the red above is arm 2 rather than an unrelated failure.
    monkeypatch.setattr(gate, "AUDIT_RENDERER_EXEMPT", "test: a reason with an expiry")
    assert main(["x", str(missing)]) == 0


@pytest.mark.unit
def test_arm_2_needs_the_renderer_to_be_WIRED_not_merely_present(tmp_path, capsys) -> None:
    """A renderer that exists and is never called does not satisfy arm 2.

    The discriminating case the `DEFERRED` entry says is owed. Arm 2 used to
    match `Object.entries(details)` anywhere in the file, so replacing the
    column's `cell` with `() => null` left `renderDetails` defined, the regex
    still matched, and the gate stayed GREEN over an audit viewer that
    rendered no details at all -- `CLAUDE.md`'s "a function with no callers",
    in the gate written to catch exactly that.

    Measured on 2026-09-21 against the real `AuditViewer.tsx`: that mutation
    left the gate at exit 0. It is now exit 1.
    """
    seed = _tree(
        tmp_path,
        schema=_SCHEMA,
        web="const t: Thing = d;\nt.excluded_inputs;",
        audit_renderer=True,
    )
    assert main(["x", str(seed)]) == 0
    capsys.readouterr()

    # Keep the iteration, delete only the WIRING.
    viewer = tmp_path / "apps" / "web" / "src" / "components" / "admin" / "AuditViewer.tsx"
    before = viewer.read_text(encoding="utf-8")
    assert before.count("cell:") == 1, "the fixture must carry exactly one cell to remove"
    viewer.write_text(
        before.replace("cell: (e) => renderDetails(e.details),", ""), encoding="utf-8"
    )
    assert "Object.entries(details)" in viewer.read_text(
        encoding="utf-8"
    ), "the iteration must SURVIVE, or this proves nothing about wiring"

    assert main(["x", str(seed)]) == 1
    assert "nothing renders the audit `details` payload generically" in capsys.readouterr().out


# --- #473: a type declaration is not a use ----------------------------------------------

_INTERFACE_ONLY = """
export interface ThingData {
  onPick: (id: string) => void;
  nested: { depth: number };
  excluded_inputs: string[];
}
export function panel(data: ThingData): string {
  return "nothing about the field";
}
"""


def test_a_field_only_DECLARED_in_an_interface_is_a_violation(tmp_path, capsys) -> None:
    """#473's shape. The interface names the subject and the field, and nothing
    renders the field. The old predicate cleared it. The field comes AFTER an
    arrow type and a nested object on purpose: a strip that counted the `>` of
    `=>`, or stopped at the nested `}`, would end early and leave it visible."""
    seed = _tree(tmp_path, schema=_SCHEMA, web=_INTERFACE_ONLY)
    assert main(["x", str(seed)]) == 1
    assert "thing.py::ThingResponse.excluded_inputs" in capsys.readouterr().out


def test_a_field_declared_AND_used_in_the_same_file_passes(tmp_path) -> None:
    web = _INTERFACE_ONLY + "export const n = (d: ThingData) => d.excluded_inputs.length;\n"
    seed = _tree(tmp_path, schema=_SCHEMA, web=web)
    assert main(["x", str(seed)]) == 0


@pytest.mark.parametrize(
    "web",
    [
        "type ThingData = {\n  excluded_inputs: string[];\n};\nexport const x = 1;\n",
        "type ThingData =\n  { excluded_inputs: string[] } | null;\nexport const x = 1;\n",
        "const t: Thing = d; // excluded_inputs is shown elsewhere\n",
        "const t: Thing = d;\n/* excluded_inputs,\n   still not rendered */\n",
    ],
    ids=["type-alias", "type-alias-next-line", "line-comment", "block-comment"],
)
def test_a_type_alias_or_a_comment_is_not_a_use(tmp_path, capsys, web: str) -> None:
    seed = _tree(tmp_path, schema=_SCHEMA, web=web)
    assert main(["x", str(seed)]) == 1
    assert "thing.py::ThingResponse.excluded_inputs" in capsys.readouterr().out


def test_a_double_slash_inside_a_string_does_not_hide_the_use(tmp_path) -> None:
    # The comment stripper is string-aware: `//` in a URL is not a comment, so
    # the use after it on the same line still counts.
    web = 'const t: Thing = d; const u = "https://x/y"; const n = t.excluded_inputs;\n'
    seed = _tree(tmp_path, schema=_SCHEMA, web=web)
    assert main(["x", str(seed)]) == 0


def test_the_subject_may_live_only_in_the_type_name(tmp_path) -> None:
    # The subject is matched against the WHOLE file: a reader that names its
    # model only in the interface it declares still attributes, as long as the
    # field is USED outside the declaration.
    web = "interface ThingData { id: string }\nexport const f = (d: any) => d.excluded_inputs;\n"
    seed = _tree(tmp_path, schema=_SCHEMA, web=web)
    assert main(["x", str(seed)]) == 0


# --- #631 round 1: what the stripper cannot parse is could-not-look ---------------------

_USE = "const t: Thing = d;\nconst n = t.excluded_inputs.length;\n"


@pytest.mark.parametrize(
    ("web", "cause"),
    [
        ("/* a comment that never closes\n" + _USE, "a /* block comment never closes"),
        ("const s = `a template that never closes\n" + _USE, "a template literal never closes"),
        (
            "interface ThingData {\n  excluded_inputs: string[];\n" + _USE,
            "an interface body never closes",
        ),
        (
            "type ThingData = { excluded_inputs: string[] }\n" + _USE.replace(";", ""),
            "a type alias body never closes",
        ),
        ('type Quote = "unterminated;\n' + _USE, "string inside a type body never closes"),
        # Open at the very END, no newline after: the EOF branch, not the
        # newline one (review of the red-on-revert run: this was untested).
        (_USE + 'type Quote = "unterminated', "string inside a type body never closes"),
    ],
    ids=["block-comment", "template", "interface", "type-alias", "string-in-type", "string-at-eof"],
)
def test_what_the_stripper_cannot_parse_is_could_not_look(
    tmp_path, capsys, web: str, cause: str
) -> None:
    # Each state used to fall through to a VERDICT: EOF taken as the end, so a
    # render after it was stripped (a red no exemption could clear) or a
    # comment stayed in (a green). Now it is exit 2, naming the file and cause.
    seed = _tree(tmp_path, schema=_SCHEMA, web=web)
    assert main(["x", str(seed)]) == 2
    err = capsys.readouterr().err
    assert "LatestPanel.tsx: could not parse" in err and cause in err, err


def test_a_brace_in_a_string_type_does_not_swallow_the_render(tmp_path) -> None:
    # `type Brace = "{";` opened a body that never closed, and the strip ate
    # the render below it. Strings are skipped inside type bodies.
    seed = _tree(tmp_path, schema=_SCHEMA, web='type Brace = "{";\n' + _USE)
    assert main(["x", str(seed)]) == 0


def test_a_regex_with_a_quote_does_not_stop_comment_stripping(tmp_path, capsys) -> None:
    # `/["']/` read as code opened a phantom string, so the comment after it on
    # the same line survived and cleared the field -- #473's own case, green.
    web = "const t: Thing = d;\nconst r = /[\"']/; // excluded_inputs is shown elsewhere\n"
    seed = _tree(tmp_path, schema=_SCHEMA, web=web)
    assert main(["x", str(seed)]) == 1
    assert "thing.py::ThingResponse.excluded_inputs" in capsys.readouterr().out


def test_an_apostrophe_in_jsx_text_does_not_swallow_the_file(tmp_path) -> None:
    # A `'` string cannot cross a newline, so JSX text like `Don't` resets at
    # the line end instead of hiding every use after it, or failing to parse.
    web = "const t: Thing = d;\nconst p = <p>Don't</p>;\nconst n = t.excluded_inputs;\n"
    seed = _tree(tmp_path, schema=_SCHEMA, web=web)
    assert main(["x", str(seed)]) == 0


def test_a_comment_after_a_jsx_apostrophe_line_is_still_stripped(tmp_path, capsys) -> None:
    # The other half of the reset: without it the phantom `'` runs to EOF and
    # every later comment is kept, so a field named only in one clears.
    web = "const t: Thing = d;\nconst p = <p>Don't</p>;\n// excluded_inputs is shown elsewhere\n"
    seed = _tree(tmp_path, schema=_SCHEMA, web=web)
    assert main(["x", str(seed)]) == 1
    assert "thing.py::ThingResponse.excluded_inputs" in capsys.readouterr().out


@pytest.mark.parametrize(
    "web",
    [
        "export function Panel({ excluded_inputs }: ThingProps) {\n"
        "  return excluded_inputs.length;\n}\n",
        "const t: Thing = d;\nconst s = `${t.excluded_inputs.length} dropped`;\n",
    ],
    ids=["destructured-prop", "template-use"],
)
def test_real_uses_are_KEPT(tmp_path, web: str) -> None:
    # What must survive the strip, not only what must go: a destructured prop
    # and a use inside a template literal are uses.
    seed = _tree(tmp_path, schema=_SCHEMA, web=web)
    assert main(["x", str(seed)]) == 0


def test_a_commented_out_audit_renderer_is_not_a_renderer(tmp_path, capsys) -> None:
    # Arm 2's twin of #473: the regexes read the RAW file, so a commented-out
    # cell satisfied them. They now read `ts_use_text`.
    seed = _tree(tmp_path, schema=_SCHEMA, web=_USE)
    viewer = tmp_path / "apps" / "web" / "src" / "components" / "admin" / "AuditViewer.tsx"
    viewer.write_text(
        "const pairs = Object.entries(details);\n// cell: (e) => renderDetails(e.details),\n",
        encoding="utf-8",
    )
    assert main(["x", str(seed)]) == 1
    assert "nothing renders the audit `details` payload generically" in capsys.readouterr().out
