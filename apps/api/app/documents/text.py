"""Shared document text extraction (N2, for #1071; design note rev 4, 15.2).

ONE reader set, ONE set of limits and ONE "not read" vocabulary, for EV-1's
evidence-link job (P4) and EV-2's client summary. Both import this module;
neither reimplements a reader ("same as" enforced by calling).

Readers: PDF (pypdf), DOCX (python-docx), XLSX (openpyxl) and plain text.
Images, legacy Office files and other archives are `not_read: unsupported_type`
until OCR and further readers exist.

**"I could not read it" and "it was empty" are different results.** A file
that cannot be read is `status="not_read"` with a typed reason and NO text; a
file that was read and holds nothing is `status="read"` with zero characters.
`DocText` refuses any shape that blurs the two (CLAUDE.md, the silent-success
rule: the "could not look" branch must never share the "nothing there" branch).

The type is decided from the file's MAGIC BYTES. The declared type (the
upload's mime and the title's extension) is a claim checked against them: a
declaration that disagrees with the bytes is `unreadable`, never trusted.

Wired to nothing yet: no route and no AI call reads it.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import zip_longest
from typing import Literal, Protocol, get_args

from app.config import Settings, get_settings
from app.logging import get_logger
from app.models.artifact import Artifact

_log = get_logger(__name__)

NotReadReason = Literal[
    "unsupported_type",
    "no_text_layer",
    "encrypted",
    "unreadable",
    "too_large",
    "storage_missing",
]

#: The whole "not read" vocabulary, for the one copy map both consumers render.
NOT_READ_REASONS: tuple[str, ...] = get_args(NotReadReason)


@dataclass(frozen=True)
class DocText:
    """What one file yielded.

    `chars_total` is the length of the WHOLE extracted text; `text` is cut to
    the limit and `truncated` says so. `pages_without_text` counts PDF pages
    that gave no text (a partly scanned file); it is 0 for every other type.
    It is an addition to section 15.2's shape: without it a PDF with one text
    page and forty scanned ones reads as a complete `read`.
    """

    status: Literal["read", "not_read"]
    reason: NotReadReason | None
    text: str
    chars_total: int
    truncated: bool
    pages_without_text: int = 0

    def __post_init__(self) -> None:
        if self.status == "read":
            if self.reason is not None:
                raise ValueError(f"a read result carries no reason, got {self.reason!r}")
            return
        if self.status != "not_read":
            raise ValueError(f"unknown status {self.status!r}")
        if self.reason not in NOT_READ_REASONS:
            raise ValueError(
                f"not_read needs a reason from {NOT_READ_REASONS}, got {self.reason!r}"
            )
        if self.text or self.chars_total or self.truncated or self.pages_without_text:
            raise ValueError("a not_read result carries no text and no counts")


@dataclass(frozen=True)
class ChunkPlan:
    """The chunks to send, and how many were sent and skipped. `sent` is
    `len(chunks)`; `skipped` is how many more the text needed past the cap."""

    chunks: tuple[str, ...]
    sent: int
    skipped: int


@dataclass(frozen=True)
class ExtractLimits:
    """The one set of limits. Built from settings by `extract_limits`."""

    max_bytes: int
    max_unzipped_bytes: int
    max_chars: int
    chunk_chars: int
    max_chunks: int


def extract_limits(settings: Settings | None = None) -> ExtractLimits:
    """The limits as configured (`shield_document_*` in app/config.py)."""
    s = settings if settings is not None else get_settings()
    return ExtractLimits(
        max_bytes=s.shield_document_max_bytes,
        max_unzipped_bytes=s.shield_document_max_unzipped_bytes,
        max_chars=s.shield_document_max_chars,
        chunk_chars=s.shield_document_chunk_chars,
        max_chunks=s.shield_document_max_chunks,
    )


class _Readable(Protocol):
    def get(self, key: str) -> bytes: ...


Kind = Literal["pdf", "docx", "xlsx", "txt", "image", "ole", "zip"]

_MIME_KIND: dict[str, Kind] = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "text/plain": "txt",
    "text/csv": "txt",
    "text/markdown": "txt",
    "application/msword": "ole",
    "application/vnd.ms-excel": "ole",
    "application/zip": "zip",
}

_EXT_KIND: dict[str, Kind] = {
    "pdf": "pdf",
    "docx": "docx",
    "xlsx": "xlsx",
    "txt": "txt",
    "csv": "txt",
    "md": "txt",
    "png": "image",
    "jpg": "image",
    "jpeg": "image",
    "gif": "image",
    "tif": "image",
    "tiff": "image",
    "bmp": "image",
    "webp": "image",
    "doc": "ole",
    "xls": "ole",
    "zip": "zip",
}

_IMAGE_MAGIC = (
    b"\x89PNG\r\n\x1a\n",
    b"\xff\xd8\xff",
    b"GIF87a",
    b"GIF89a",
    b"II*\x00",
    b"MM\x00*",
    b"BM",
)
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


class _NotRead(Exception):
    """Internal: a reader decided the file is not read, and why."""

    def __init__(self, reason: NotReadReason, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


def document_text(storage: _Readable, artifact: Artifact, *, limits: ExtractLimits) -> DocText:
    """Extract one artifact's text, or say exactly why it was not read.

    A storage MISS (`FileNotFoundError`, which every backend raises for one) is
    `storage_missing`. Any other storage failure propagates: an unreachable
    store is not a fact about the file and must not be recorded as one.
    """
    try:
        data = storage.get(artifact.file_storage_key)
    except FileNotFoundError:
        return _not_read(artifact, "storage_missing", "no object at the storage key")
    try:
        raw, pages_without_text = _extract(data, artifact, limits)
    except _NotRead as nr:
        return _not_read(artifact, nr.reason, nr.detail)
    text = _sanitize(raw)
    chars_total = len(text)
    truncated = chars_total > limits.max_chars
    result = DocText(
        status="read",
        reason=None,
        text=text[: limits.max_chars] if truncated else text,
        chars_total=chars_total,
        truncated=truncated,
        pages_without_text=pages_without_text,
    )
    _log.info(
        "documents.text.read",
        artifact_id=str(artifact.id),
        chars_total=chars_total,
        truncated=truncated,
        pages_without_text=pages_without_text,
    )
    return result


def _not_read(artifact: Artifact, reason: NotReadReason, detail: str) -> DocText:
    _log.warning(
        "documents.text.not_read",
        artifact_id=str(artifact.id),
        reason=reason,
        detail=detail,
    )
    return DocText(status="not_read", reason=reason, text="", chars_total=0, truncated=False)


def _extract(data: bytes, artifact: Artifact, limits: ExtractLimits) -> tuple[str, int]:
    if len(data) > limits.max_bytes:
        raise _NotRead("too_large", f"{len(data)} bytes over the {limits.max_bytes} byte limit")
    detected = _detect(data, limits)
    declared = _declared(artifact)
    mismatched = sorted(d for d in declared if d != detected)
    if mismatched:
        raise _NotRead("unreadable", f"declared {mismatched} but the bytes are {detected}")
    if detected in ("image", "ole", "zip"):
        raise _NotRead("unsupported_type", f"{detected} has no text reader")
    if detected == "pdf":
        return _read_pdf(data)
    if detected == "docx":
        return _read_docx(data), 0
    if detected == "xlsx":
        return _read_xlsx(data), 0
    return _read_txt(data), 0


def _declared(artifact: Artifact) -> set[Kind]:
    """The kinds the upload CLAIMS, from its mime and its title's extension.
    A generic mime (octet-stream) or no known extension claims nothing."""
    kinds: set[Kind] = set()
    mime = (artifact.mime_type or "").split(";")[0].strip().lower()
    if mime in _MIME_KIND:
        kinds.add(_MIME_KIND[mime])
    elif mime.startswith("image/"):
        kinds.add("image")
    title = artifact.title or ""
    if "." in title:
        ext = title.rsplit(".", 1)[1].lower()
        if ext in _EXT_KIND:
            kinds.add(_EXT_KIND[ext])
    return kinds


def _detect(data: bytes, limits: ExtractLimits) -> Kind:
    """The kind the BYTES are. Anything without a known signature is a text
    candidate; `_read_txt` decides whether it really is text."""
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(_OLE_MAGIC):
        return "ole"
    if data.startswith(_IMAGE_MAGIC) or (data[:4] == b"RIFF" and data[8:12] == b"WEBP"):
        return "image"
    if data.startswith(b"PK\x03\x04"):
        return _detect_zip(data, limits)
    return "txt"


def _detect_zip(data: bytes, limits: ExtractLimits) -> Kind:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos = z.infolist()
    except (zipfile.BadZipFile, EOFError, ValueError) as exc:
        raise _NotRead("unreadable", f"zip container: {type(exc).__name__}: {exc}") from exc
    inflated = sum(i.file_size for i in infos)
    if inflated > limits.max_unzipped_bytes:
        raise _NotRead(
            "too_large",
            f"parts inflate to {inflated} bytes, over the {limits.max_unzipped_bytes} byte limit",
        )
    names = {i.filename for i in infos}
    if "word/document.xml" in names:
        return "docx"
    if "xl/workbook.xml" in names:
        return "xlsx"
    return "zip"


def _read_pdf(data: bytes) -> tuple[str, int]:
    from pypdf import PdfReader
    from pypdf.errors import FileNotDecryptedError

    try:
        reader = PdfReader(io.BytesIO(data))
        texts = [page.extract_text() or "" for page in reader.pages]
    except FileNotDecryptedError as exc:
        # pypdf tries the empty user password itself, which opens
        # owner-password-only files (any viewer opens those too). This is
        # raised only for a file that needs a password we do not have.
        raise _NotRead("encrypted", f"PDF: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - typed and logged, never swallowed
        # pypdf raises a wide family on a damaged file (PdfReadError, its
        # stream errors, and KeyError/ValueError from deep inside a parse).
        # Every one means the same thing to a caller: this file was not read.
        raise _NotRead("unreadable", f"PDF: {type(exc).__name__}: {exc}") from exc
    without = sum(1 for t in texts if not t.strip())
    if without == len(texts):
        raise _NotRead("no_text_layer", f"none of {len(texts)} pages has a text layer")
    return "\n".join(t for t in texts if t.strip()), without


def _read_docx(data: bytes) -> str:
    from docx import Document

    try:
        doc = Document(io.BytesIO(data))
        parts: list[str] = []
        seen_headers: set[str] = set()
        for section in doc.sections:
            for header in (section.first_page_header, section.header, section.even_page_header):
                _add_unique(parts, seen_headers, header.iter_inner_content())
        parts.extend(_docx_blocks(doc.iter_inner_content()))
        seen_footers: set[str] = set()
        for section in doc.sections:
            for footer in (section.first_page_footer, section.footer, section.even_page_footer):
                _add_unique(parts, seen_footers, footer.iter_inner_content())
    except Exception as exc:  # noqa: BLE001 - typed and logged, never swallowed
        raise _NotRead("unreadable", f"DOCX: {type(exc).__name__}: {exc}") from exc
    return "\n".join(parts)


def _add_unique(parts: list[str], seen: set[str], blocks: Iterator[object]) -> None:
    """A header linked to the previous section repeats its text; keep one."""
    text = "\n".join(_docx_blocks(blocks))
    if text.strip() and text not in seen:
        seen.add(text)
        parts.append(text)


def _docx_blocks(blocks: Iterator[object]) -> Iterator[str]:
    from docx.table import Table

    for block in blocks:
        if isinstance(block, Table):
            for row in block.rows:
                cells: list[str] = []
                last = None
                for cell in row.cells:
                    # A merged cell is returned once per grid column it spans.
                    if cell._tc is last:
                        continue
                    last = cell._tc
                    cells.append(cell.text)
                yield "\t".join(cells)
        else:
            yield block.text  # type: ignore[attr-defined]


def _read_xlsx(data: bytes) -> str:
    from openpyxl import load_workbook

    try:
        values = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        formulas = load_workbook(io.BytesIO(data), read_only=True, data_only=False)
        parts: list[str] = []
        for ws_v, ws_f in zip(values.worksheets, formulas.worksheets, strict=True):
            parts.append(f"[Sheet: {ws_v.title}]")
            rows_v = ws_v.iter_rows(values_only=True)
            rows_f = ws_f.iter_rows(values_only=True)
            for row_v, row_f in zip_longest(rows_v, rows_f, fillvalue=()):
                line = _xlsx_row(row_v, row_f)
                if line:
                    parts.append(line)
        values.close()
        formulas.close()
    except Exception as exc:  # noqa: BLE001 - typed and logged, never swallowed
        raise _NotRead("unreadable", f"XLSX: {type(exc).__name__}: {exc}") from exc
    return "\n".join(parts)


def _xlsx_row(row_v: tuple, row_f: tuple) -> str:
    """One row, tab-joined. A formula with no cached value keeps its formula
    text: a blank cell would read as "nothing there", which is not what the
    file holds."""
    cells: list[str] = []
    for value, formula in zip_longest(row_v, row_f, fillvalue=None):
        if value is None and isinstance(formula, str) and formula.startswith("="):
            value = formula
        cells.append("" if value is None else str(value))
    while cells and cells[-1] == "":
        cells.pop()
    return "\t".join(cells)


def _read_txt(data: bytes) -> str:
    """UTF-8 (with or without a BOM) and BOM-marked UTF-16 are read. Anything
    else is `unreadable`: guessing an encoding puts mojibake into a quote that
    then reads as the client's own words."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError as exc:
            raise _NotRead("unreadable", f"text: UTF-16 BOM but {exc}") from exc
    if b"\x00" in data:
        raise _NotRead("unreadable", "text: NUL bytes, so binary rather than text")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise _NotRead("unreadable", f"text: not UTF-8 ({exc})") from exc


#: Line separators other than "\n", including "\r\n" as one.
_LINE_BREAKS = re.compile("\r\n|[\r\v\f\x1c\x1d\x1e\x85\u2028\u2029]")
#: Every other control character: C0 except tab and newline, DEL, and C1.
_CONTROLS = re.compile("[\x00-\x08\x0e-\x1b\x7f-\x84\x86-\x9f]")


def _sanitize(text: str) -> str:
    """One newline convention and no control characters, for every reader.
    A removed control becomes a space so the words either side stay apart."""
    return _CONTROLS.sub(" ", _LINE_BREAKS.sub("\n", text.lstrip("\ufeff")))


def chunk_text(text: str, *, chunk_chars: int, max_chunks: int) -> ChunkPlan:
    """Split `text` into chunks of at most `chunk_chars`, breaking after the
    last whitespace in a window where there is one, so a word is not split.
    The chunks concatenate back to the text exactly. At most `max_chunks` are
    returned; the count the rest of the text needed is `skipped`."""
    if not isinstance(text, str):
        raise TypeError(f"chunk_text needs str, got {type(text).__name__}")
    if chunk_chars < 1:
        raise ValueError(f"chunk_chars must be at least 1, got {chunk_chars}")
    if max_chunks < 1:
        raise ValueError(f"max_chunks must be at least 1, got {max_chunks}")
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_chars, len(text))
        if end < len(text):
            window = text[start:end]
            cut = max(window.rfind(" "), window.rfind("\n"), window.rfind("\t"))
            if cut > 0:
                end = start + cut + 1
        chunks.append(text[start:end])
        start = end
    sent = chunks[:max_chunks]
    plan = ChunkPlan(chunks=tuple(sent), sent=len(sent), skipped=len(chunks) - len(sent))
    _log.info("documents.text.chunked", sent=plan.sent, skipped=plan.skipped)
    return plan
