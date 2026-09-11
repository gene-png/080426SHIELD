"""A CSF Playbook must say on the PAGE whether it was approved (#277).

#274 labels a Playbook exported from an unapproved assessment by prefixing the
filename `WORKING_`. The label exists only there. The documents themselves say
nothing about approval status, so the guarantee is stated in the one place a
reader is least likely to look.

#243's threat is a consultant downloading the file and handing it over out of
band. **A filename survives an email attachment. It does not survive being
opened, printed, re-saved under another name, or pasted into a deck** — which
is most of what happens to a document handed over that way. The client is then
looking at a cover page that says `Prepared for: {their name}` and nothing
else.

## "Working profile" is not a warning, and that is the trap

Three cover sites carry the only status-adjacent text there is:

    cover.append([f"Working profile version: {version}"])
    Paragraph(f"Working profile version: {version}", ...)
    meta = [f"Prepared for: {client_name}", f"Working profile version: {version}"]

**"Working profile" is CSF 2.0's own vocabulary for a normal artifact of the
method** — the profile you work in, as opposed to the target profile. A reader
who knows the method reads it as the name of the thing, which is what it is. It
is present on an APPROVED playbook too. So it cannot carry the warning, and a
test asserting on that phrase would pass for both states and prove nothing.

## Both states are asserted, not just the dangerous one

An unapproved document must SAY it is unapproved; an approved one must say it
is approved. Stating only the first makes silence ambiguous — a reader cannot
tell an approved document from one rendered by a build that predates the
stamp. That is the same reason `#102`'s withholding rule needed a persisted row
for "nothing was cited" rather than an absent one.

## The export is NOT gated, and must not become gated

#274's reasoning is kept intact: the Export button is offered whenever profiles
are seeded, and a consultant reads their own working profile in order to decide
whether to approve it. `CLAUDE.md`'s #32 shape — the guarantee needs the
artifact to SAY WHAT IT IS, not the export forbidden. This issue is about
WHERE it says it.
"""

from __future__ import annotations

import io
import zipfile
from types import SimpleNamespace

import pytest

from app.csf import playbook_export

#: Rows in the shape the renderers actually read. Built with the same fields
#: `test_playbook_export_content.py` uses rather than invented here -- a
#: hand-guessed fixture agrees with nothing and fails on the first attribute
#: the renderer reaches for, which is exactly what the first draft of this file
#: did (`tier_levels`, `enterprise_level` and `rollup_rule` all missing).
_ROWS = [
    SimpleNamespace(
        subcategory_code="GV.OC-01",
        name="Organizational context",
        function="GV",
        tier_levels={"high": 2, "moderate": 3, "low": 4},
        enterprise_level=2,
        rollup_rule=6,
        target_level=4,
        gap=True,
        priority=1,
    ),
]


def _xlsx_text(blob: bytes) -> str:
    """Every string in the workbook, including the shared-string table."""
    out = []
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for name in z.namelist():
            if name.endswith(".xml"):
                out.append(z.read(name).decode("utf-8", "replace"))
    return "\n".join(out)


def _pdf_text(blob: bytes) -> str:
    """Extracted, not scanned as bytes.

    A first draft decoded the raw PDF as latin-1 and searched that. reportlab
    compresses its content streams, so the notice was ON the cover and
    unfindable -- the test failed for BOTH states, which is the tell that the
    extractor and not the code was wrong. `pypdf` is what every other PDF
    assertion in this suite uses.
    """
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(blob))
    return "".join(page.extract_text() for page in reader.pages)


def _docx_text(blob: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        return z.read("word/document.xml").decode("utf-8", "replace")


#: Every renderer that produces a client-readable CSF Playbook, with the
#: extractor for its format. Derived by reading the `render_*` definitions in
#: `playbook_export.py` rather than listing the ones this issue happened to
#: name -- a renderer left out is a document that says nothing, which is the
#: whole defect.
_RENDERERS = [
    ("render_xlsx", _xlsx_text, {"tier_profiles": {}}),
    ("render_exec_pdf", _pdf_text, {}),
    ("render_full_pdf", _pdf_text, {}),
    ("render_exec_docx", _docx_text, {}),
    ("render_full_docx", _docx_text, {}),
]


def _render(name: str, *, approved: bool, extra: dict) -> bytes:
    fn = getattr(playbook_export, name)
    return fn(
        client_name="Atlas Manufacturing",
        version=3,
        enterprise_rows=_ROWS,
        approved=approved,
        **extra,
    )


@pytest.mark.unit
def test_every_playbook_renderer_takes_an_approval_status() -> None:
    """Fail loudly if a renderer is added without one.

    The parametrised tests below can only check the renderers named in
    `_RENDERERS`. This asserts the list still matches the module, so a sixth
    renderer cannot ship silently unstamped while the sweep reports clean.
    """
    import inspect

    found = {
        n
        for n, obj in vars(playbook_export).items()
        if n.startswith("render_") and inspect.isfunction(obj)
    }
    listed = {n for n, _, _ in _RENDERERS}
    assert found == listed, (
        f"the playbook renderers and this file's list disagree: "
        f"only in module {sorted(found - listed)}, only in list "
        f"{sorted(listed - found)}. A renderer missing from the list is a "
        f"document that can ship with no approval status on it."
    )

    for name in sorted(found):
        sig = inspect.signature(getattr(playbook_export, name))
        assert "approved" in sig.parameters, (
            f"{name} does not take an approval status, so it cannot state one. "
            f"#277: the WORKING_ label exists only in the filename."
        )


@pytest.mark.unit
@pytest.mark.parametrize("name, extract, extra", _RENDERERS)
def test_an_unapproved_playbook_says_so_on_the_page(name, extract, extra) -> None:
    """**The #277 assertion.** The document itself, not its filename."""
    text = extract(_render(name, approved=False, extra=extra))
    assert playbook_export.WORKING_NOTICE in text, (
        f"{name} renders an unapproved playbook with no notice on the page. "
        f"A filename does not survive being opened, printed or pasted into a "
        f"deck, which is the handoff #243 is actually about."
    )


@pytest.mark.unit
@pytest.mark.parametrize("name, extract, extra", _RENDERERS)
def test_an_approved_playbook_does_not_carry_the_notice(name, extract, extra) -> None:
    """The positive control, and it is what keeps the notice meaningful.

    A notice printed on every document is furniture by the second one. Without
    this, stamping unconditionally would satisfy the test above.
    """
    text = extract(_render(name, approved=True, extra=extra))
    assert playbook_export.WORKING_NOTICE not in text, (
        f"{name} prints the unapproved notice on an APPROVED playbook. A "
        f"warning that is always there is read as furniture."
    )


@pytest.mark.unit
@pytest.mark.parametrize("name, extract, extra", _RENDERERS)
def test_an_approved_playbook_states_that_it_is_approved(name, extract, extra) -> None:
    """Silence must not be the only signal for the safe state.

    If only the unapproved case were stamped, a reader could not distinguish an
    approved document from one produced by a build that predates the stamp --
    absence of a warning is not evidence of approval.
    """
    text = extract(_render(name, approved=True, extra=extra))
    assert playbook_export.APPROVED_NOTICE in text, (
        f"{name} says nothing about approval on an approved playbook, so the "
        f"absence of a warning is doing the work, and absence is not evidence."
    )


@pytest.mark.unit
def test_the_notice_is_not_the_methods_own_vocabulary() -> None:
    """ "Working profile" is a CSF artifact name, not a warning.

    It appears on an APPROVED playbook too, so a notice built from that phrase
    would be invisible exactly where it matters. This pins the distinction the
    issue turns on.
    """
    approved = _xlsx_text(_render("render_xlsx", approved=True, extra={"tier_profiles": {}}))
    assert "Working profile version" in approved, (
        "the method's own vocabulary disappeared from an approved playbook; if "
        "that is deliberate this test should be rewritten, but it means the "
        "phrase can no longer be assumed present in both states"
    )
    assert playbook_export.WORKING_NOTICE not in approved
    assert "Working profile version" not in playbook_export.WORKING_NOTICE, (
        "the unapproved notice is built out of the method's own artifact name, "
        "so it cannot be told apart from ordinary CSF vocabulary"
    )
