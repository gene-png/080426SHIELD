"""One reading of `Client.legal_name` for every surface that prints it.

D-080 (#254) made the column nullable: NULL means nobody has named the
organisation. The rule it stated was "one representation of unnamed, and one
rendering of it" — and the branch that stated it left SIX readers deciding for
themselves, each with a bare `client_legal_name or "Client"`.

**A bare `or` is satisfied by `"   "`.** So a blank name never reached the
`"Client"` fallback: it rendered as EMPTY on the organisation line of a client's
DOCX, PDF and XLSX, while the admin UI called the same row unnamed because the
web helper trims. That is two definitions of "named" disagreeing about one row,
which is the defect D-080 exists to close, surviving at the read end.

Migration 0050 removes the blanks that are already stored. This module is the
other half, and the two are not alternatives: 0050 clears the rows that exist,
this stops one that arrives any other way — a direct SQL fix-up, a restored
backup, a future writer that forgets to normalise.

**Why a function rather than the same expression six times.** Five exporters and
the admin fulfill path were byte-identical copies of the wrong thing, which is
how they were all wrong together and why the fix has to be a call rather than a
sixfold edit. `CLAUDE.md`: a claim that two surfaces agree is enforced by
CALLING the same code, never by writing it twice.
"""

from __future__ import annotations

#: Printed wherever an unnamed organisation needs a label on a DELIVERABLE.
#:
#: Deliberately not the web layer's "(pending intake)": this string goes on a
#: document a consultant hands to a client, where an internal workflow status
#: would be the wrong register. The web label is `UNNAMED_ORG_LABEL` in
#: `apps/web/src/lib/org-name.ts` and the two are allowed to differ.
UNNAMED_ORG_FALLBACK = "Client"


def is_named_org(legal_name: str | None) -> bool:
    """True when a human has given this organisation a name.

    Blank-or-missing is ONE question with one answer, which is the whole point:
    `None`, `""` and `"   "` all mean nobody has named it, and a caller that
    has to remember which of the three it might be holding will eventually
    forget one. The API's own `not (x or "").strip()` guards say the same thing
    inline; this is that predicate with a name.
    """
    return bool(legal_name and legal_name.strip())


def org_display_name(legal_name: str | None) -> str:
    """The organisation's name for a rendered surface, or the fallback.

    Returns the name STRIPPED, so a stored `"  Acme  "` does not reach a title
    or a filename with its padding — `slugify` would collapse it, but the DOCX
    and PDF organisation lines do not go through `slugify`.
    """
    return legal_name.strip() if is_named_org(legal_name) else UNNAMED_ORG_FALLBACK
