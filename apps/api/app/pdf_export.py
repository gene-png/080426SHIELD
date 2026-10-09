"""Text for reportlab PDFs, printed as text and never as markup (#775).

The PDF twin of `app/docx_export.py`, shared by every service's `render_pdf`.

reportlab's `Paragraph` parses its input as markup. A string that is not a
literal -- a client's legal name, a service title a consultant typed, a catalog
name -- must not reach it unescaped. Measured with reportlab 5.0.1, through a
real `Paragraph`, text read back with pypdf (2026-10-09):

    | input                                      | unescaped          | escaped       |
    | ------------------------------------------ | ------------------ | ------------- |
    | "ATT&CK Coverage"                          | "ATT&CK; Coverage" | as typed      |
    | "R&D <Labs> Co"                            | "R&D; Co"          | as typed      |
    | "Acme </b> Inc"                            | raises ValueError  | as typed      |
    | "A&O modifications"                        | "A&O; modifications" | as typed    |
    | "Identity Federation & User Credentialing" | as typed           | as typed      |
    | "Acme & Co."                               | as typed           | as typed      |
    | "x < y"                                    | as typed           | as typed      |

Only `&` directly followed by a word character garbles, and a `<` either drops
text or fails the whole export. `html.escape(s, quote=False)` escapes exactly
`&`, `<` and `>`, the three characters the markup reads, so every string prints
as itself, and a string the markup already printed correctly prints the same.

THE INVARIANT, greppable: inside a `render_pdf`, every `Paragraph(` is
`pdf_text(...)`, or a literal, or an f-string of literal markup whose every
interpolation goes through `pdf_escape`. DOCX and XLSX are plain text and must
NOT use this: they would print `&amp;`.
"""

from __future__ import annotations

import html
from typing import Any


def pdf_escape(s: str) -> str:
    """`s` escaped for reportlab markup: `&`, `<` and `>` only."""
    return html.escape(s, quote=False)


def pdf_text(s: str, style: Any) -> Any:
    """A `Paragraph` that prints `s` exactly as written."""
    from reportlab.platypus import Paragraph

    return Paragraph(pdf_escape(s), style)
