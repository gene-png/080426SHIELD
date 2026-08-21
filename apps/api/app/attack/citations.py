"""Resolve a model's tool citation to a capability on the client's approved list.

The ATT&CK mapping may only cite tools the client actually owns, so every cited
string is checked against the capability list. That check is exact-match today
and the failures are SILENT: a citation that misses by a word is dropped, and the
technique it was meant to cover either reads as a gap or keeps a `covered` status
with an empty tool list. "Gap" then means "the model phrased the name wrong",
which is indistinguishable in the report from "the client has no control here" —
and a fabricated gap is exactly the failure N-033 shipped, 607 of them.

Enriching the payload with `vendor` and `category` makes the near miss MORE
likely, not less: the model then has three plausible strings per tool where it
had one. So a near miss must be resolved, not counted after the fact.

Resolution is deterministic rather than fuzzy. Edit-distance matching would
happily rank "Splunk Phantom" and "Splunk Enterprise" as equally good homes for
"Splunk" and silently attribute coverage to whichever sorted first.

**The invariant: every rule here finds EXACTLY ONE candidate or gives up.** An
earlier implementation stated this and never held it — two consecutive patches
each looked done and each was wrong, both found only by adversarial audit while
CI stayed green. This is written against the invariant rather than patched
toward it, and the four paths that broke it are named tests.

## Three outcomes, not two

A citation the resolver had to CHANGE to make match is an INFERENCE, and
inference is not confirmation however plausible it looks (5.1, owner-confirmed
2026-08-08).

* **CONFIRMED** — matched after case and whitespace normalisation ONLY. There is
  nothing to be wrong about.
* **NEEDS_REVIEW** — resolved, but something had to be changed or assumed.
  Applied and visible, and queued for a human.
* **REJECTED** — no unique candidate. Counted and visible; the citation is gone.

The line is drawn at case/whitespace deliberately and is not an implementer's
call: the wider reading — nothing confirmed without a human, exact matches
included — reports 0% coverage on every fresh run until a consultant walks all
633 techniques. Do not move it here; that is a decision to take to the owner.

Ambiguity REJECTS rather than guessing, per the accuracy tiebreak: a dropped
citation is counted and visible, a wrong attribution is invisible and reaches the
client.

## Scope note

This module decides what a citation MEANS. It does not decide what a technique is
WORTH -- `app/attack/pending.py` does, and `analytics.compute` applies it.

That sentence has now been wrong in both directions, which is why it is spelled
out rather than assumed:

* One draft claimed 5.1 "is enforced on the technique STATUS in `analytics.py`"
  while no code anywhere consulted a citation's outcome. Describing a control
  that does not exist is worse than deferring one, because it reads to the next
  person as covered.
* The correction to that then said the enforcement "is the fix and is not here",
  and described a technique whose every citation was rejected keeping `covered`
  with an EMPTY tool list and carrying full weight in `coverage_pct` and the
  client PDF. That was true of W2 and false from #102 onward.

What holds now: `run_ai` still assigns `row.status` from the model independently
of what happens to that row's citations, and it MUST -- clearing a citation has
to be able to put the technique back into whichever status it says, so the status
has to survive underneath. What changed is that the status no longer scores on
its own.

For that to be decidable at all, the outcomes are persisted per row
(`attack_coverage.unconfirmed_citations`, migration 0044) instead of living in
the run response, which is what finally made "queued for a human" a true
statement -- see `CitationOutcome.inferred` and `.rejected_details`. Note that
`rejected_details` exists even though a rejection resolves to no tool name: it is
the only thing separating "we dropped this row's evidence" from "nobody ever
cited anything for this row", and those two must score differently.

"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

_PUNCT = re.compile(r"[^a-z0-9]+")
_WS = re.compile(r"\s+")

_MAX_REJECTED_EXAMPLES = 5


def _norm(value: str) -> str:
    """Case and whitespace only — the CONFIRMED key.

    Deliberately does NOT touch punctuation. `_fold` does, and conflating the two
    is defect #11: the old code folded the candidate name and merely case-folded
    the citation, so a punctuated name could never compare equal to itself and
    every verbatim citation of `Tenable.io`, `AT&T Cybersecurity` or `F5 BIG-IP`
    was reported as a near miss. Harmless while it was log noise; a false
    statement a consultant can act on once the counter was surfaced.
    """
    return _WS.sub(" ", value.casefold()).strip()


def _fold(value: str) -> str:
    """Case, whitespace AND punctuation — the MATCHING key."""
    return _PUNCT.sub(" ", value.casefold()).strip()


class ReviewReason(StrEnum):
    """Why a resolved citation is an inference rather than a confirmation."""

    PUNCTUATION = "punctuation"
    SUBSTRING = "substring"
    VENDOR = "vendor"
    #: Uniqueness could not be established because some candidate has no vendor
    #: recorded. It may well be the same vendor as the citation; the list does
    #: not say, and guessing is the original defect.
    INCOMPLETE_VENDOR_DATA = "incomplete_vendor_data"


@dataclass(frozen=True)
class Candidate:
    """A capability the model is allowed to cite."""

    name: str
    vendor: str | None = None


@dataclass(frozen=True)
class Resolution:
    """What one cited string resolved to."""

    name: str | None
    confirmed: bool = False
    review_reason: ReviewReason | None = None
    #: "unknown" (no candidate) or "ambiguous" (more than one). None when resolved.
    rejected_reason: str | None = None


class CitationResolver:
    """Maps a cited string to a canonical capability name, or refuses.

    Built once per run: the indexes are small (tens of tools) and this is called
    once per cited string across ~633 techniques.
    """

    def __init__(self, candidates: list[Candidate]) -> None:
        self._candidates = list(candidates)
        self._by_norm: dict[str, set[str]] = {}
        self._by_fold: dict[str, set[str]] = {}
        self._by_vendor: dict[str, set[str]] = {}
        #: Candidates with no vendor recorded. Their vendor COULD be the cited
        #: string, so any vendor-shaped resolution is unverifiable while one of
        #: these is on the list — the nullable-vendor bypass, defect 1.
        self._vendorless: set[str] = set()
        for c in candidates:
            self._by_norm.setdefault(_norm(c.name), set()).add(c.name)
            self._by_fold.setdefault(_fold(c.name), set()).add(c.name)
            if c.vendor and c.vendor.strip():
                self._by_vendor.setdefault(_fold(c.vendor), set()).add(c.name)
            else:
                self._vendorless.add(c.name)

    def resolve(self, cited: str) -> Resolution:
        if not isinstance(cited, str) or not cited.strip():
            return Resolution(name=None, rejected_reason="unknown")

        # --- CONFIRMED: case and whitespace only, no inference ---------------
        exact = self._by_norm.get(_norm(cited))
        if exact and len(exact) == 1:
            return Resolution(name=next(iter(exact)), confirmed=True)
        if exact:
            # Two capabilities differing only by case or whitespace. Refusing to
            # guess between them IS the invariant.
            return Resolution(name=None, rejected_reason="ambiguous")

        key = _fold(cited)
        if not key:
            return Resolution(name=None, rejected_reason="unknown")

        # --- gather every candidate ANY rule would accept, then judge ONCE ---
        #
        # Defects 2 and 3 were both this: the rules were consulted in sequence
        # and each judged uniqueness against its OWN index. The substring rule
        # found one name and returned; when it found two it fell through to the
        # vendor rule, which resolved anyway. And a citation naming one
        # capability while vending another ("VMware Carbon Black" v:Broadcom
        # beside "Workspace ONE" v:VMware) looked unique to both indexes
        # separately and to neither together.
        #
        # Uniqueness is a property of the UNION. Judge it once, on the union.
        by_fold = self._by_fold.get(key, set())
        by_vendor = self._by_vendor.get(key, set())
        by_substring = {
            c.name
            for c in self._candidates
            if re.search(rf"(?:^|\s){re.escape(key)}(?:\s|$)", _fold(c.name))
        }
        pool = by_fold | by_vendor | by_substring

        if not pool:
            return Resolution(name=None, rejected_reason="unknown")
        if len(pool) > 1:
            return Resolution(name=None, rejected_reason="ambiguous")

        name = next(iter(pool))

        # --- exactly one candidate: an inference, and which kind -------------
        #
        # Defect 1. A vendor-shaped match is only as trustworthy as the vendor
        # column. `Duo Security` with no vendor may well be Cisco's; the list
        # does not say. Resolving "Cisco" to `Cisco Umbrella` on that basis is
        # what credited a DNS filter with Duo's brute-force prevention, and
        # counted it as a success. A name-only match (`by_fold`) is unaffected —
        # it never consulted the vendor column.
        vendor_shaped = bool(by_vendor or (by_substring and not by_fold))
        others_without_vendor = self._vendorless - {name}
        if vendor_shaped and others_without_vendor:
            return Resolution(name=name, review_reason=ReviewReason.INCOMPLETE_VENDOR_DATA)
        if by_fold:
            return Resolution(name=name, review_reason=ReviewReason.PUNCTUATION)
        if by_substring:
            return Resolution(name=name, review_reason=ReviewReason.SUBSTRING)
        return Resolution(name=name, review_reason=ReviewReason.VENDOR)


@dataclass
class CitationOutcome:
    """What resolving one technique's citations produced.

    `confirmed + needs_review + rejected` equals the number of usable cited
    strings. A surfaced number that does not add up is worse than no number, so
    the invariant is asserted rather than assumed.
    """

    tools: list[str] = field(default_factory=list)
    #: The subset of `tools` whose citation was an inference. Retained and
    #: applied — 5.1 is explicit that flagged is visible and kept, not dropped —
    #: but a consultant needs to know WHICH, not merely how many.
    needs_review_tools: list[str] = field(default_factory=list)
    #: The same tools keyed by WHY. Without this the nullable-vendor guard was
    #: inert: it computed `INCOMPLETE_VENDOR_DATA` and nothing read it, so a
    #: vendor guess made against a list with missing vendors was reported
    #: identically to a trivial punctuation rescue. Deleting the guard changed no
    #: observable behaviour, which meant `test_defect_1` was green over a defect
    #: that still shipped. These are not equally risky and must not read alike.
    needs_review_by_reason: dict[str, list[str]] = field(default_factory=dict)
    #: Cited entries that were not usable strings at all — a bare string where a
    #: list belongs, a null, an empty name. Previously skipped with no counter,
    #: so `confirmed + needs_review + rejected` silently understated what the
    #: model sent and the row's tools were overwritten with nothing.
    unusable: int = 0
    confirmed: int = 0
    needs_review: int = 0
    rejected: int = 0
    #: Verbatim, bounded. "GV.OC-1" tells you the catalogue holds "GV.OC-01";
    #: a bare count tells you nothing.
    rejected_examples: list[str] = field(default_factory=list)
    #: Per-citation records for the two outcomes that are NOT confirmations, in
    #: the shape `attack_coverage.unconfirmed_citations` stores (#101). The
    #: summary fields above are deduplicated and bounded because they are read
    #: once by a human; these are unbounded and keep the string the model
    #: ACTUALLY sent, because they are the row's audit record and "Qradar" is the
    #: part a consultant acts on -- `needs_review_tools` only carries what the
    #: resolver turned it into.
    #:
    #: `inferred` entries name the tool they applied. `rejected` entries carry
    #: `tool: None`: they applied nothing, and a rejection that could pass for a
    #: tool name would cancel out a real one.
    inferred: list[dict] = field(default_factory=list)
    rejected_details: list[dict] = field(default_factory=list)


def _retract_inference(out: CitationOutcome, name: str) -> None:
    """Drop the row-level record that `name` was inferred, keeping the counters.

    `confirmed` / `needs_review` describe what the MODEL sent, and it really did
    write one name that had to be rescued -- those stay. What is retracted is the
    per-row evidence record, which is the thing #102 scores on and the thing a
    consultant is asked to review. Leaving a review item for a capability the
    model also cited exactly would queue work with no question in it.
    """
    out.inferred = [e for e in out.inferred if e["tool"] != name]
    out.needs_review_tools = [t for t in out.needs_review_tools if t != name]
    for reason, tools in list(out.needs_review_by_reason.items()):
        remaining = [t for t in tools if t != name]
        if remaining:
            out.needs_review_by_reason[reason] = remaining
        else:
            del out.needs_review_by_reason[reason]


def resolve_citations(names: object, resolver: CitationResolver) -> CitationOutcome:
    """Resolve a list of cited tool names, preserving order and de-duplicating.

    Two citations resolving to the same capability collapse to one — the model
    naming both "CrowdStrike" and "CrowdStrike Falcon Enterprise" means one tool,
    and recording it twice would overstate coverage.
    """
    out = CitationOutcome()
    if not isinstance(names, list):
        # A bare string where a list belongs is a real shape drift, and the row's
        # tools get overwritten with nothing either way. Count it rather than
        # returning an empty outcome that reads as "the model cited nothing".
        out.unusable = 1
        return out
    seen: set[str] = set()
    for cited in names:
        # Not a citation at all. Kept OUT of `rejected` — that number means "the
        # model named a tool we could not place", and inflating it would blunt
        # the thing a consultant acts on — but counted, because the alternative
        # is a silent discard, which is the defect this module exists to end.
        if not isinstance(cited, str) or not cited.strip():
            out.unusable += 1
            continue
        res = resolver.resolve(cited)
        if res.name is None:
            out.rejected += 1
            if len(out.rejected_examples) < _MAX_REJECTED_EXAMPLES:
                out.rejected_examples.append(cited)
            out.rejected_details.append(
                {"cited": cited, "reason": f"rejected_{res.rejected_reason}"}
            )
            continue
        if res.confirmed:
            out.confirmed += 1
        else:
            out.needs_review += 1
        if res.name not in seen:
            seen.add(res.name)
            out.tools.append(res.name)
            if not res.confirmed:
                out.needs_review_tools.append(res.name)
                reason = res.review_reason.value if res.review_reason else "unknown"
                out.needs_review_by_reason.setdefault(reason, []).append(res.name)
                out.inferred.append({"tool": res.name, "cited": cited, "reason": reason})
        elif res.confirmed:
            # A CONFIRMED citation of a capability something earlier in this list
            # only INFERRED. It retracts the inference: the model named the
            # approved string exactly, so there is nothing left to be wrong
            # about, and arriving second makes that no weaker.
            #
            # Without this, list ORDER decided whether the technique scored --
            # `["CrowdStrike", "CrowdStrike Falcon"]` withheld the row and the
            # reverse order scored it, on identical evidence. Harmless while it
            # fed a display counter; #102 promoted it to a client-facing coverage
            # number. Found by the §14 audit.
            _retract_inference(out, res.name)
    return out
