"""#254 contract: a self-serve signup's email never becomes the org's legal name.

`Client.legal_name` is the string printed on the organisation line of every
client deliverable. Self-service provisioning (D-034) used to derive it from
the registrant's email -- the domain for an unknown company domain, and the
registrant's own DISPLAY NAME for a generic provider -- so a deliverable could
carry `acme.example`, or a person's name, as the client organisation.

**Both write paths are covered here on purpose.** They are two calls to one
helper in `routes/auth.py` and they leak different things, so a fix verified
against one of them says nothing about the other. The generic-provider path is
the worse of the two: a domain reads as a system placeholder, whereas a
person's name on the organisation line is PII on a delivered document.

WHAT THE SPEC SAYS, which is where the expected values come from rather than
from the code under test:

  * D-080 -- `legal_name` is NULL until a human names the organisation. A
    self-serve registrant has named nothing, so the column records nothing.
  * Master Spec Sec 15.5, restated in `tech_debt/filename.py`'s own docstring --
    the company slug of an empty name is the literal `Unknown`.

The world these tests build is a registration request. They do NOT construct a
`Client` row, because writing the row is the step under test: a setup that
stamped `legal_name` itself would prove the assertion against its own fixture
(CLAUDE.md, "a test that supplies its own precondition from the thing under
test cannot fail").
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture()
def app_client(tmp_path) -> Iterator[tuple[TestClient, sessionmaker]]:
    db_path = tmp_path / "shield-self-serve.db"
    url = f"sqlite:///{db_path}"
    os.environ["DATABASE_URL"] = url

    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    test_engine = create_engine(url, future=True)
    TestSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False, future=True)

    from app.db.session import get_db
    from app.main import create_app

    def override_get_db() -> Iterator[Session]:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        yield c, TestSession


def _register(client: TestClient, *, email: str, display_name: str) -> dict:
    r = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "correct horse battery staple!",
            "display_name": display_name,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


# The two self-serve write paths, and the string each one used to leak.
#
# `must_not_appear` is what the test WROTE INTO the world (an address it chose,
# a display name it chose), never a value read back out of the code under test.
_SELF_SERVE_PATHS = [
    pytest.param(
        "newhire@acme-unregistered.example",
        "Dana Whitfield",
        "acme-unregistered.example",
        id="unknown-company-domain",
    ),
    pytest.param(
        "dana.whitfield@gmail.com",
        "Dana Whitfield",
        "Dana Whitfield",
        id="generic-provider-is-a-persons-name",
    ),
]


@pytest.mark.unit
@pytest.mark.parametrize(("email", "display_name", "must_not_appear"), _SELF_SERVE_PATHS)
def test_self_serve_provisioning_records_no_derived_legal_name(
    app_client: tuple[TestClient, sessionmaker],
    email: str,
    display_name: str,
    must_not_appear: str,
) -> None:
    """The store records that nobody has named the org -- not a guess at one."""
    client, TestSession = app_client
    _register(client, email="founder@kentro.example", display_name="Bootstrap Admin")

    body = _register(client, email=email, display_name=display_name)
    cid = body["user"]["client_id"]
    assert cid is not None, "a self-serve registrant must land in its own tenant"
    cid = uuid.UUID(cid)

    from app.models.client import Client

    with TestSession() as db:
        row = db.get(Client, cid)
        assert row is not None
        # D-080: NULL is the record of "no name was offered", which is the
        # condition every downstream guard needs and the only one the row can
        # state without a second field to keep in sync.
        assert row.legal_name is None, (
            f"self-serve provisioning stored {row.legal_name!r} as the organisation's "
            f"legal name; it must store NULL until a human names the org"
        )
        assert row.legal_name != must_not_appear


@pytest.mark.unit
@pytest.mark.parametrize(("email", "display_name", "must_not_appear"), _SELF_SERVE_PATHS)
def test_self_serve_legal_name_never_reaches_a_deliverable(
    app_client: tuple[TestClient, sessionmaker],
    email: str,
    display_name: str,
    must_not_appear: str,
) -> None:
    """The client-reachable surface: the filename on the document they download.

    This asserts through `deliverable_filename` rather than through the stored
    column, because the column is not what the client reads. Every finalize
    route builds its filenames from a bare `client.legal_name` read, and that
    read is reproduced here.

    The needle is the SLUGIFIED form. A raw-string check would pass while the
    defect was live -- Sec 15.5 strips `.` and `-` and turns a space into `_`,
    so `Dana Whitfield` reaches the filename as `Dana_Whitfield` and
    `"Dana Whitfield" not in name` is satisfied by a filename that carries the
    person's name in full.
    """
    client, TestSession = app_client
    _register(client, email="founder@kentro.example", display_name="Bootstrap Admin")

    body = _register(client, email=email, display_name=display_name)
    cid = uuid.UUID(body["user"]["client_id"])

    from app.models.client import Client
    from app.tech_debt.filename import SERVICE_SLUG_ATTACK, deliverable_filename, slugify

    with TestSession() as db:
        org = db.get(Client, cid).legal_name

    name = deliverable_filename(
        company=org,
        service_slug=SERVICE_SLUG_ATTACK,
        extension="pdf",
        day=date(2026, 9, 22),
        version=1,
    )
    leaked = slugify(must_not_appear)
    assert leaked not in name, (
        f"the deliverable filename {name!r} carries {leaked!r}, which came from the "
        f"registrant's email rather than from a name the organisation gave"
    )
    # Sec 15.5's documented empty-company behaviour, quoted in filename.py's
    # module docstring: "empty result -> Unknown".
    assert name.startswith("Unknown_")


@pytest.mark.unit
@pytest.mark.parametrize(("email", "display_name", "must_not_appear"), _SELF_SERVE_PATHS)
def test_self_serve_legal_name_never_reaches_the_ai_egress_path(
    app_client: tuple[TestClient, sessionmaker],
    email: str,
    display_name: str,
    must_not_appear: str,
) -> None:
    """The second surface an unnamed org can leak through: the Tech Debt extractor.

    `client_org_name_for_tenant` is what feeds the tenant's own name to the
    redactor as a name hint. An unnamed tenant has no name to hint with, and
    handing it the registrant's personal name would put that name into the
    prompt built to keep names OUT.
    """
    client, TestSession = app_client
    _register(client, email="founder@kentro.example", display_name="Bootstrap Admin")

    body = _register(client, email=email, display_name=display_name)
    cid = uuid.UUID(body["user"]["client_id"])

    from app.tech_debt.extract import client_org_name_for_tenant

    with TestSession() as db:
        resolved = client_org_name_for_tenant(db, cid)

    assert resolved is None, (
        f"the Tech Debt extractor resolved {resolved!r} as this tenant's organisation "
        f"name; a self-serve tenant that has completed no intake has none"
    )
    assert resolved != must_not_appear


@pytest.mark.unit
def test_admin_created_client_keeps_its_name(
    app_client: tuple[TestClient, sessionmaker],
) -> None:
    """The exemption, pinned so the fix cannot over-reach.

    `routes/admin.py`'s create-client path is a human naming an organisation,
    and it stays. This test is the reason the guards are keyed on the NAME
    being absent rather than on `intake_completed_at` being NULL: an
    admin-created tenant has a real name and never completes intake, so keying
    on intake would blank its deliverables and block its engagements -- a
    regression strictly worse than the defect being fixed.
    """
    client, TestSession = app_client
    admin = _register(client, email="founder@kentro.example", display_name="Bootstrap Admin")
    bearer = admin["tokens"]["access_token"]

    created = client.post(
        "/admin/clients",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"legal_name": "Northwind Grid Cooperative"},
    )
    assert created.status_code == 201, created.text
    cid = uuid.UUID(created.json()["id"])

    from app.models.client import Client
    from app.tech_debt.extract import client_org_name_for_tenant

    with TestSession() as db:
        row = db.get(Client, cid)
        assert row.legal_name == "Northwind Grid Cooperative"
        assert row.intake_completed_at is None
        assert client_org_name_for_tenant(db, cid) == "Northwind Grid Cooperative"


@pytest.mark.unit
@pytest.mark.parametrize("org_name", [None, "", "   "])
def test_provisioning_refuses_an_unnamed_org_rather_than_titling_it_none(
    org_name: str | None,
) -> None:
    """The ratchet in `provision_self_assessment_service`, pinned.

    It builds `f"{org_name} - {SERVICE_TITLES[...]}"`, so an unnamed org would
    title a consultant's workspace `"None - NIST CSF 2.0 Assessment"` -- or,
    for a blank name, put a leading space where the client's name belongs -- and
    NOTHING would error. Both live callers guard first, so this cannot fire
    today; it exists so that a third caller fails loudly instead.

    A ratchet with no test is indistinguishable from a ratchet that was deleted,
    which is why this is here rather than left to the callers' guards. The
    `sr` is a bare object: the raise happens before any attribute but `id` is
    read, so a real `ServiceRequest` row would test the same line through more
    setup.
    """
    from app.provisioning import provision_self_assessment_service

    class _Sr:
        id = "11111111-1111-4111-8111-111111111111"

    with pytest.raises(ValueError, match="named organisation"):
        provision_self_assessment_service(
            None,  # db is never touched -- the guard is the first statement
            _Sr(),  # type: ignore[arg-type]
            org_name=org_name,
            actor_user_id=uuid.uuid4(),
        )


@pytest.mark.unit
def test_provisioning_accepts_an_explicit_title_without_an_org_name() -> None:
    """The other half of the branch, so the guard cannot be 'fixed' into refusing everything.

    `create_engagement` passes a user-supplied `title`, and a named engagement
    does not need the org name to build one. A guard that refused this would
    break the self-service engagement flow, and a test of only the raising half
    would stay green through it.
    """
    from app.provisioning import provision_self_assessment_service

    class _Sr:
        id = "11111111-1111-4111-8111-111111111111"

    # Reaching the NEXT statement is the assertion: the guard did not fire.
    # It raises AttributeError on the bare stub, never ValueError.
    with pytest.raises(Exception) as excinfo:
        provision_self_assessment_service(
            None,
            _Sr(),  # type: ignore[arg-type]
            org_name=None,
            actor_user_id=uuid.uuid4(),
            title="Q3 Zero Trust review",
        )
    assert not isinstance(excinfo.value, ValueError), (
        "the guard fired despite an explicit title; a named engagement does not "
        "need an org name to build its title"
    )


@pytest.mark.unit
@pytest.mark.parametrize("unnamed", [None, "", "   ", "\t\n "])
def test_every_exporter_renders_the_fallback_for_a_blank_name(unnamed: str | None) -> None:
    """The TWIN sweep: all five services, not the one the finding named.

    Each `build_context` resolved the organisation line with a bare
    `client_legal_name or "Client"` -- five byte-identical copies of the same
    expression, which is why they were all wrong together. A blank name is
    truthy, so it skipped the fallback and rendered EMPTY where the client's
    name belongs.

    This asserts the shared resolution rather than each exporter's full
    context, because the five signatures differ and the defect was never in
    the signatures: it was in the one expression they each copied. The
    `build_context`-level assertion lives in `test_attack_exporters.py`, so the
    wiring is covered through a real exporter too -- this is the claim that the
    other four agree with it.
    """
    from app.client_naming import org_display_name

    assert org_display_name(unnamed) == "Client"


@pytest.mark.unit
def test_no_surface_turns_a_nullable_name_into_a_display_string_with_a_bare_or() -> None:
    """DERIVED sweep, replacing an iteration over a hand list of five services.

    The previous version of this guard iterated
    ``("csf", "zt", "attack", "risk", "tech_debt")`` over
    ``{service}/exporters.py`` and asserted a SUBSTRING. It had two independent
    ways to report clean over a live defect, and both fired at once:

      * the iteration set could not reach ``routes/csf.py``, where the CSF
        Playbook export did ``name = org or "Client"`` and fed FIVE client
        artifacts -- so the guard was structurally blind to the one remaining
        instance, by construction rather than by accident;
      * a substring test is satisfied by a DOCSTRING or a comment, so a file
        that merely mentions the call would have passed without making it.

    This asks the question the other way round, over every file rather than a
    list: does ANY module turn a nullable name into a display string with a
    bare ``or "..."``? A bare ``or`` is satisfied by ``"   "``, which is how a
    blank reached a client's deliverable in the first place.

    ``or ""`` is excluded deliberately -- that is the ``(x or "").strip()``
    guard idiom, which is the CORRECT shape and the thing the readers should
    be doing.

    **WHAT THIS CANNOT SEE, stated because the first version of this docstring
    claimed "an eighth reader added anywhere under ``app/`` fails this", and
    that was false.** It is a line-wise regex over four-then-seven spellings,
    so it is a FLOOR, not a census. Measured misses:

      * a ternary -- ``name = x if x else "Client"``;
      * a dict default -- ``d.get("legal_name", "Client")``;
      * an intermediate variable, where the assignment and the fallback are on
        different lines and neither line has both halves;
      * any form black has wrapped across lines, since the scan is line-wise;
      * ANYTHING in ``apps/web``: the sweep is rooted at ``apps/api/app``, and
        the eighth reader (``lib/risk/client.ts``) was in the web layer (D-082).
        Grep ``apps/web/src`` separately.

    Spellings that WERE missed and are now covered, all live in this tree for
    this exact value: ``org_name`` (the parameter of
    ``provision_self_assessment_service``), ``company`` (the
    ``deliverable_filename`` kwarg), and ``client_org_name`` -- which appears in
    twelve modules including ``ai/engine.py``, ``ai/llm.py``, ``ai/redact.py``
    and four routes.

    **THE MECHANISM, because the previous version of this docstring got it wrong
    and the wrong version would have sent the next person nowhere.** It said
    ``org_name`` was missed for an ORDERING reason -- that a leading ``org``
    alternative matched the prefix and then failed on ``_n`` -- "so the longer
    alternatives are listed FIRST". Measured: ordering is IRRELEVANT here.
    Python's ``re`` BACKTRACKS into an alternation when the remainder fails, so
    ``(org|org_name)`` and ``(org_name|org)`` both match ``org_name or "X"``.
    What fixed ``org_name`` was ADDING it, not moving it.

    Ordering WAS load-bearing where the shorter alternative COMPLETES the match
    -- ``redact.py``'s ``_redact_names`` built an alternation in which a bare
    first name plus a word boundary succeeded and swallowed the longer full
    name. Since D-088 it no longer does: every hint's matches are found on the
    text and overlapping spans are merged, so hint order decides nothing there.
    It was a different precondition, and reaching for a known-good shape
    without checking which property made it correct is what produced the false
    sentence above.

    **The real hole was PREFIX SHADOWING, and no reordering could have closed
    it.** ``client_org`` matches the prefix of ``client_org_name``, nothing
    spelled the whole identifier, and ``_`` is a word character so there is no
    word boundary between them. The group is now boundary-anchored on BOTH
    sides, which is what stops a prefix standing in for the longer identifier --
    and with that anchor, ordering genuinely does not matter.

    The behavioural cover for what a pattern cannot reach is
    ``test_a_blank_legal_name_prints_the_fallback_on_all_five_playbook_artifacts``
    in ``test_csf_playbook_export.py``, which drives the route and reads all five
    stored artifacts. This test is the cheap wide net; that one is the deep check
    on the path that actually broke.
    """
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[2] / "app"
    # A name-ish identifier, `or`, then a NON-EMPTY string literal.
    #
    # The word boundary on BOTH sides of the group is the load-bearing part:
    # without the trailing one, `client_org` matched the PREFIX of
    # `client_org_name` and the longer identifier was invisible. Ordering is NOT
    # load-bearing -- `re` backtracks into the alternation -- so this list is
    # ordered for reading rather than longest-first for matching.
    bare_fallback = re.compile(
        r"\b(?:client_legal_name|client_org_name|company_name|legal_name"
        r"|client_name|client_org|org_name|company|org)\b"
        r'\s*or\s*"[^"]+"'
    )

    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if path.name == "client_naming.py":
            continue  # the one module allowed to name the fallback
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue  # prose describing the defect is not the defect
            if bare_fallback.search(line):
                offenders.append(f"{path.relative_to(root)}:{lineno}: {stripped}")

    assert not offenders, (
        "a bare `or` on a client name is satisfied by a whitespace-only value, so "
        "a blank reaches the rendered surface instead of the fallback. Call "
        "app.client_naming.org_display_name instead. Offending lines: " + str(offenders)
    )


@pytest.mark.unit
def test_the_deliverable_surfaces_call_the_shared_resolver() -> None:
    """The positive half, asserted on PARSED CALLS rather than on source text.

    ``"org_display_name(" in src`` is satisfied by a comment or a docstring
    that mentions it -- which is exactly how the previous guard could have
    passed over a file that talked about the call without making it. Walking
    the AST for a real ``Call`` node cannot be satisfied by prose.

    The list here is a list, and says so: it names the surfaces whose output
    reaches a client artifact. The DERIVED half is the sweep above, which is
    what catches a surface nobody added here.

    **THE WALK IS MODULE-SCOPED, which is a real limit.** `routes/csf.py` and
    `routes/admin.py` are large modules with several display paths, and ONE
    call anywhere in the file satisfies this for all of them. So it proves the
    module knows about the resolver, not that every path in it uses one --
    combined with the sweep's own blind spots (a ternary, a dict default, an
    intermediate variable), a single file could satisfy both and still render
    a blank through a path neither can see.

    It is fail-CLOSED in the direction that matters, which is why it stays: an
    `ast.Attribute` call, or the import being dropped, reddens it. The
    behavioural cover is
    `test_a_blank_legal_name_prints_the_fallback_on_all_five_playbook_artifacts`
    (`test_csf_playbook_export.py`), which drives the route and reads the five
    stored artifacts rather than the source.
    """
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2] / "app"
    surfaces = [
        "csf/exporters.py",
        "zt/exporters.py",
        "attack/exporters.py",
        "risk/exporters.py",
        "tech_debt/exporters.py",
        "routes/admin.py",
        "routes/csf.py",  # the seventh, found by round 5 after the other six
    ]
    for rel in surfaces:
        tree = ast.parse((root / rel).read_text(encoding="utf-8"))
        called = any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "org_display_name"
            for node in ast.walk(tree)
        )
        assert called, (
            f"{rel} does not CALL org_display_name (a mention in a comment or "
            f"docstring does not count); a bare fallback there renders a blank "
            f"organisation line for a whitespace-only name"
        )


@pytest.mark.unit
@pytest.mark.parametrize("blank", [None, "", "   "])
def test_playbook_export_renders_the_fallback_for_a_blank_name(blank: str | None) -> None:
    """The RENDERER, for the reader that carried the live defect.

    This calls `render_xlsx` with a name it resolved itself, so it cannot see
    `routes/csf.py` passing the raw value to one of its five renderers. The
    route-level assertion is
    `test_a_blank_legal_name_prints_the_fallback_on_all_five_playbook_artifacts`
    in `test_csf_playbook_export.py`, which drives `/playbook/export` and reads
    all five stored artifacts. This one pins the renderer half.

    `routes/csf.py`'s Playbook export was the seventh reader: `name = org or
    "Client"`, feeding five client artifacts. It is now fixed, and until this
    test the fix was pinned only by a source-text sweep and an AST walk --
    neither of which exercises anything.

    `CLAUDE.md` is explicit that a resolver and a pure function are not the
    surface. The scenario a source guard cannot see: `render_xlsx` refactored
    to re-derive the cover name internally, `routes/csf.py` still calling
    `org_display_name`, both source guards green, and the cover blank again.

    ATT&CK already had a `build_context`-level assertion; the route that
    actually broke had none. This is that assertion, one layer up, against the
    bytes the renderer produces.
    """
    from app.client_naming import org_display_name
    from app.csf.playbook_export import render_xlsx

    # The route's own resolution, reproduced: this is what `routes/csf.py`
    # passes as `client_name=`.
    name = org_display_name(blank)
    raw = render_xlsx(
        approved=True,
        client_name=name,
        version=1,
        enterprise_rows=[],
        tier_profiles={},
    )

    # Read the RENDERED BYTES, not the resolver's return value. Asserting
    # `name == "Client"` here would only re-test `org_display_name`, which is
    # the weakness this test exists to remove: the cover cell is what the
    # client opens.
    import io

    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(raw))
    cells = [
        str(cell.value)
        for sheet in wb.worksheets
        for row in sheet.iter_rows()
        for cell in row
        if cell.value is not None and str(cell.value).startswith("Client:")
    ]
    assert cells, "no `Client:` cover cell found -- the export shape changed"
    for cell in cells:
        assert cell == "Client: Client", (
            f"the Playbook cover reads {cell!r}. A blank name is truthy, so it "
            f"never reaches the fallback and renders as nothing where the "
            f"organisation's name belongs."
        )
