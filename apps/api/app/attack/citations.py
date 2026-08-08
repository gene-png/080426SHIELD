"""Resolve a model's tool citation to a capability on the client's approved list.

The ATT&CK mapping may only cite tools the client actually owns, so every cited
string is checked against the capability list. That check used to be exact-match
and the failures were SILENT: a citation that missed by a word was dropped and
the technique it was meant to cover went on to read as a gap. "Gap" then means
"the model phrased the name wrong", which is indistinguishable in the report from
"the client has no control here" — and a fabricated gap is exactly the failure
N-033 shipped.

Enriching the payload with `vendor` and `category` made the near-miss more
likely, not less: the model now has three plausible strings per tool where it had
one. So a near miss must be RESOLVED, not counted after the fact.

Resolution is deliberately deterministic rather than fuzzy. Edit-distance
matching would happily rank "Splunk Phantom" and "Splunk Enterprise" as equally
good homes for "Splunk", and would silently attribute coverage to whichever
sorted first. Every rule here either finds EXACTLY ONE candidate or gives up:
attributing a control to the wrong tool is worse than dropping the citation,
because a wrong attribution is invisible while a drop is counted.

Rules, most conservative first:

1. Exact, case- and whitespace-insensitive.
2. Punctuation-insensitive ("Tenable.io" == "Tenable io").
3. The citation is a distinct prefix/substring of exactly one capability
   ("CrowdStrike" -> "CrowdStrike Falcon Enterprise").
4. The citation is exactly one capability's vendor.

Anything ambiguous or unrecognised is unresolved and reported.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PUNCT = re.compile(r"[^a-z0-9]+")


def _fold(value: str) -> str:
    """Case, whitespace and punctuation folded — the comparison key."""
    return _PUNCT.sub(" ", value.casefold()).strip()


@dataclass(frozen=True)
class Candidate:
    """A capability the model is allowed to cite."""

    name: str
    vendor: str | None = None


class CitationResolver:
    """Maps a cited string to a canonical capability name, or to None.

    Built once per run: the indexes are small (tens of tools) and the resolver is
    called once per cited string across ~633 techniques.
    """

    def __init__(self, candidates: list[Candidate]) -> None:
        self._names = [c.name for c in candidates]
        self._exact: dict[str, set[str]] = {}
        self._vendors: dict[str, set[str]] = {}
        for c in candidates:
            self._exact.setdefault(_fold(c.name), set()).add(c.name)
            if c.vendor and c.vendor.strip():
                self._vendors.setdefault(_fold(c.vendor), set()).add(c.name)

    def resolve(self, cited: str) -> tuple[str | None, bool]:
        """Return (canonical name or None, was_normalised).

        `was_normalised` is True when the citation did not match exactly and had
        to be resolved — an inference worth counting and logging, because it is
        the system deciding what the model meant.
        """
        if not isinstance(cited, str) or not cited.strip():
            return None, False
        key = _fold(cited)
        if not key:
            return None, False

        # 1 + 2. Exact after folding. Ambiguity here would mean two capabilities
        # differing only by punctuation or case, which we refuse to guess between.
        exact = self._exact.get(key)
        if exact and len(exact) == 1:
            name = next(iter(exact))
            return name, _fold(name) != cited.strip().casefold()
        if exact:
            return None, False

        # 3. A distinct substring of exactly one capability. Guarded on word
        # boundaries so "Okta" cannot resolve via "Diagnostokta".
        subs = {n for n in self._names if re.search(rf"(?:^|\s){re.escape(key)}(?:\s|$)", _fold(n))}
        if len(subs) == 1:
            return next(iter(subs)), True

        # 4. Exactly one capability carries this vendor.
        vendor = self._vendors.get(key)
        if vendor and len(vendor) == 1:
            return next(iter(vendor)), True

        return None, False


@dataclass
class CitationOutcome:
    """What resolving one technique's citations produced."""

    tools: list[str]
    normalised: int = 0
    rejected: int = 0
    rejected_examples: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.rejected_examples is None:
            self.rejected_examples = []


def resolve_citations(names: object, resolver: CitationResolver) -> CitationOutcome:
    """Resolve a list of cited tool names, preserving order and de-duplicating.

    Two citations resolving to the same capability collapse to one — the model
    naming both "CrowdStrike" and "CrowdStrike Falcon Enterprise" means one tool,
    and recording it twice would overstate coverage.
    """
    out = CitationOutcome(tools=[])
    if not isinstance(names, list):
        return out
    seen: set[str] = set()
    for cited in names:
        if not isinstance(cited, str):
            continue
        name, normalised = resolver.resolve(cited)
        if name is None:
            out.rejected += 1
            if len(out.rejected_examples) < 5:
                out.rejected_examples.append(cited)
            continue
        if normalised:
            out.normalised += 1
        if name not in seen:
            seen.add(name)
            out.tools.append(name)
    return out
