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
        # `1`, not `"P1"` as `test_playbook_export_content.py` uses. The
        # renderers fall through on both (`_PRIORITY_ORDER.get(1, 3)` and
        # `r.priority == "P1"`), so the exec PDF prints "No gaps were
        # identified" over this row -- harmless for the approval assertions
        # here, and stated because the comment above says these fields were
        # taken from that file and this one field was not.
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
    # THE FOURTH CELL OF THE MATRIX, and the only one whose failure hands a
    # client a false assurance. The first draft asserted three of four:
    # (unapproved -> WORKING present), (approved -> WORKING absent),
    # (approved -> APPROVED present). Nothing said a DRAFT must not ALSO claim
    # approval -- so rewriting `_approval_notice` to append rather than choose,
    # or adding an unconditional banner, would have shipped a document reading
    # "Approved by Kentro." and the warning together, with every test green.
    assert playbook_export.APPROVED_NOTICE not in text, (
        f"{name} prints the APPROVED notice on an unapproved playbook. A "
        f"client reads the reassuring sentence, not the second one."
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


@pytest.mark.unit
def test_the_notice_lands_on_the_FIRST_sheet_of_the_workbook() -> None:
    """`_xlsx_text` reads every sheet, so it cannot see tab order.

    `routes/csf.py` claims the status is stamped on "the cover and the first
    sheet". The property holds today because `wb.create_sheet("About", 0)`
    passes an explicit index -- drop that `0` and the notice moves to the last
    tab, the client opens onto `Enterprise Profile`, and every other test here
    stays green because the string is still somewhere in the package.
    """
    from openpyxl import load_workbook

    wb = load_workbook(
        io.BytesIO(_render("render_xlsx", approved=False, extra={"tier_profiles": {}}))
    )
    assert wb.sheetnames[0] == "About", (
        f"the notice sheet is no longer first: {wb.sheetnames}. A client opens "
        f"on whatever is, and the approval status is not on it."
    )
    cells = [str(c.value) for row in wb["About"].iter_rows() for c in row if c.value is not None]
    assert any(
        playbook_export.WORKING_NOTICE in c for c in cells
    ), "the About sheet is first but does not carry the notice"


# ---------------------------------------------------------------------------
# #294 — on EVERY page, not only the cover.
# ---------------------------------------------------------------------------
#
# The tests above extract the whole document as one string, so a cover-only
# stamp satisfies every one of them. That is not a weakness in them -- it is
# exactly the scope #277 claimed -- but it means nothing already written can
# tell the two states apart, and the per-page assertions have to read a
# different surface per format rather than the same blob harder.
#
# "Page" is not the same object in the three formats, so each extractor returns
# the list of things a reader can be looking at IN ISOLATION:
#
#   PDF   -> one entry per rendered page.
#   DOCX  -> one entry per section FOOTER, which is what Word repeats per page.
#            Reading `word/document.xml` here would pass on the cover paragraph
#            and prove nothing, which is the trap this whole file is about.
#   XLSX  -> one entry per worksheet. A workbook has no pages on screen, so the
#            unit a reader can be looking at alone is the sheet.


def _pdf_pages(blob: bytes) -> list[str]:
    from pypdf import PdfReader

    return [page.extract_text() for page in PdfReader(io.BytesIO(blob)).pages]


def _docx_footers(blob: bytes) -> list[str]:
    """Section footers, read through python-docx rather than by unzipping.

    `word/footer1.xml` is only the part python-docx happens to write first; a
    document with two sections has `footer2.xml` as well, and a name-based read
    would quietly check one of them. Going through `doc.sections` asks the
    format which footer applies to what.
    """
    from docx import Document

    doc = Document(io.BytesIO(blob))
    return ["\n".join(p.text for p in s.footer.paragraphs) for s in doc.sections]


def _xlsx_sheets(blob: bytes) -> list[str]:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(blob))
    return [
        "\n".join(str(c.value) for row in ws.iter_rows() for c in row if c.value is not None)
        for ws in wb.worksheets
    ]


#: Same renderer set as `_RENDERERS`, with the per-page extractor for each. The
#: two lists are pinned against each other below rather than merged, because
#: `_RENDERERS` is itself checked against the module: merging would leave one
#: derivation where there are two independent ones.
_PER_PAGE = [
    ("render_xlsx", _xlsx_sheets, {"tier_profiles": {}}),
    ("render_exec_pdf", _pdf_pages, {}),
    ("render_full_pdf", _pdf_pages, {}),
    ("render_exec_docx", _docx_footers, {}),
    ("render_full_docx", _docx_footers, {}),
]


@pytest.mark.unit
def test_every_renderer_has_a_per_page_extractor() -> None:
    """A renderer in one list and not the other is an unstamped document.

    Without this, adding a sixth renderer to `_RENDERERS` alone would leave the
    per-page sweep silently covering five of six while reporting clean -- the
    shape `test_every_playbook_renderer_takes_an_approval_status` exists to
    stop one level up.
    """
    assert {n for n, _, _ in _PER_PAGE} == {n for n, _, _ in _RENDERERS}


@pytest.mark.unit
@pytest.mark.parametrize("name, surfaces, extra", _PER_PAGE)
def test_an_unapproved_playbook_says_so_on_EVERY_page(name, surfaces, extra) -> None:
    """**The #294 assertion**, and the one the cover-only tests cannot make.

    #277's own argument is that a filename fails because it does not survive
    being "pasted into a deck". The page that gets pasted is the scorecard or
    the roadmap table, not page 1 of ~25 -- so a cover-only stamp fails the
    same test it was justified by.
    """
    pages = surfaces(_render(name, approved=False, extra=extra))
    assert pages, f"{name} produced no readable page at all, so nothing was checked"
    missing = [i for i, text in enumerate(pages) if playbook_export.WORKING_NOTICE not in text]
    assert not missing, (
        f"{name}: {len(missing)} of {len(pages)} pages carry no approval notice "
        f"(indexes {missing}). A page handed over on its own says nothing about "
        f"the assessment being unapproved, which is #294."
    )


@pytest.mark.unit
@pytest.mark.parametrize("name, surfaces, extra", _PER_PAGE)
def test_no_page_of_an_unapproved_playbook_claims_approval(name, surfaces, extra) -> None:
    """The fourth matrix cell, per page rather than per document.

    The document-level version of this already exists above. It is repeated
    here because the two can now disagree: a per-page stamp that prints
    unconditionally, or one keyed on the wrong side of the boolean, puts
    "Approved by Kentro." in the footer of a draft while the cover correctly
    says the opposite -- and the whole-document assertion above would still be
    green, because it only asks whether the string is somewhere.
    """
    for i, text in enumerate(surfaces(_render(name, approved=False, extra=extra))):
        assert playbook_export.APPROVED_NOTICE not in text, (
            f"{name} page {i} of an UNAPPROVED playbook claims approval. A "
            f"reader takes the reassuring sentence, not the other one."
        )


@pytest.mark.unit
@pytest.mark.parametrize("name, surfaces, extra", _PER_PAGE)
def test_an_approved_playbook_carries_its_own_status_per_page(name, surfaces, extra) -> None:
    """Both directions, per page.

    Stamping every page of a DRAFT and nothing on an approved document would
    pass every assertion above. Then a page extracted from an approved playbook
    is indistinguishable from a page produced before #294 existed, which is the
    reason `APPROVED_NOTICE` exists at all.
    """
    pages = surfaces(_render(name, approved=True, extra=extra))
    assert pages
    for i, text in enumerate(pages):
        assert playbook_export.APPROVED_NOTICE in text, (
            f"{name} page {i} of an APPROVED playbook says nothing, so absence "
            f"is doing the work and absence is not evidence."
        )
        assert (
            playbook_export.WORKING_NOTICE not in text
        ), f"{name} page {i} of an APPROVED playbook carries the draft warning."


@pytest.mark.unit
def test_the_full_pdf_is_long_enough_for_this_to_mean_something() -> None:
    """A one-page PDF makes "every page" and "the cover" the same claim.

    The per-page tests above would pass over a single-page document while
    proving nothing, and the fixture here is one subcategory -- so the length
    is a property of the fixture, not of the product, and it needs saying out
    loud rather than assuming ~25 pages because the docstring says so.
    """
    pages = _pdf_pages(_render("render_full_pdf", approved=False, extra={}))
    assert len(pages) > 1, (
        f"the full playbook rendered {len(pages)} page(s) from this fixture, so "
        f"the per-page assertions above are indistinguishable from the "
        f"cover-only ones and #294 is not actually being tested"
    )


@pytest.mark.unit
def test_every_data_sheet_freezes_its_banner() -> None:
    """A banner that scrolls away is a cover, one row down.

    `_xlsx_sheets` reads cell values, so it cannot see whether the notice stays
    on screen -- a sheet with the banner at row 1 and no freeze passes every
    assertion above and hides the notice the moment the reader scrolls, which
    is what happens immediately on a 106-row profile.

    `About` is exempt and says so: it carries the notice in its body, it is the
    first tab a client opens onto, and it is short enough not to scroll.
    """
    from openpyxl import load_workbook

    wb = load_workbook(
        io.BytesIO(_render("render_xlsx", approved=False, extra={"tier_profiles": {}}))
    )
    for ws in wb.worksheets:
        if ws.title == "About":
            continue
        assert (
            str(ws["A1"].value or "") == playbook_export.WORKING_NOTICE
        ), f"sheet {ws.title!r} does not open with the notice: {ws['A1'].value!r}"
        assert ws.freeze_panes == "A3", (
            f"sheet {ws.title!r} freezes at {ws.freeze_panes!r}, not A3 — the "
            f"banner (row 1) and the header (row 2) must both stay on screen."
        )


@pytest.mark.unit
def test_the_banner_leaves_no_gap_above_the_data() -> None:
    """The frozen row must be the first DATA row, not a blank one.

    Introduced and caught while building #294: setting the freeze with
    `ws.freeze_panes = ws.cell(row=row + 1, column=1)` asks openpyxl for a cell
    and thereby CREATES it, which moves the sheet's insertion point past it. So
    every data sheet gained an empty row between the headings and the records,
    and the freeze pointed at the blank.

    A read that is also a write leaves no trace in the diff -- the line looks
    like it locates a cell. This pins the OUTCOME (the row under the freeze
    holds a record) rather than the spelling, so any future way of producing
    the same gap fails here too.
    """
    from openpyxl import load_workbook

    wb = load_workbook(
        io.BytesIO(_render("render_xlsx", approved=False, extra={"tier_profiles": {}}))
    )
    for ws in wb.worksheets:
        if ws.title == "About":
            continue
        first = int(str(ws.freeze_panes)[1:])
        assert ws.cell(row=first, column=1).value is not None, (
            f"sheet {ws.title!r} freezes at row {first}, which is empty — the "
            f"banner or the header left a gap above the data."
        )


@pytest.mark.unit
def test_the_banner_does_not_swallow_the_sheet() -> None:
    """The stamp must not be the reason the data is unreadable.

    `_autofit` sizes a column to its longest cell, and the notice is ~110
    characters. Sized to it, column A is wider than the screen and every other
    column is pushed off — so the change that makes the status impossible to
    miss would make the sheet impossible to read, and nothing else here would
    notice.
    """
    from openpyxl import load_workbook

    wb = load_workbook(
        io.BytesIO(_render("render_xlsx", approved=False, extra={"tier_profiles": {}}))
    )
    ws = wb["Enterprise Profile"]
    width = ws.column_dimensions["A"].width
    assert width is not None and width <= 30, (
        f"column A is {width} wide, sized to the banner rather than to the "
        f"subcategory codes under it"
    )


@pytest.mark.unit
def test_the_notice_wording_is_pinned_literally() -> None:
    """Every other test reads the constant from the module under test.

    So shortening the notice to "Draft" would ship green -- the assertions
    would compare the module's string to itself. `check_test_integrity`'s TI001
    cannot see it either: it visits `ImportFrom` of UPPER_SNAKE names, and
    these are attribute reads off an imported module.

    This is the one place the client-facing WORDS are written out, so a change
    to them is a deliberate act with a red test attached rather than a silent
    edit to copy a client reads.
    """
    assert playbook_export.WORKING_NOTICE == (
        "NOT APPROVED - working draft. This playbook has not been approved by "
        "Kentro and its content may change."
    )
    assert playbook_export.APPROVED_NOTICE == "Approved by Kentro."
