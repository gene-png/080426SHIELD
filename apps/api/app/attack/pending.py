"""Decide whether a technique's status is backed by CONFIRMED support (#102 / 5.1).

`analytics.py` takes `pending_codes` and does not care where they came from. This
is where they come from: the rule that turns a stored row -- its status, its
`unconfirmed_citations` (migration 0044), and its tool lists -- into the one
question that matters, *may this status score?*

## The rule (5.1, owner-confirmed 2026-08-08 -- not re-litigated here)

    A technique's status counts toward the score only when it is backed by a
    CONFIRMED citation -- not merely a resolved one, and not a flagged one.

Confirmed means one of two things, and only these two:

* the model cited a name that matched after case/whitespace normalisation only,
  so there was nothing to be wrong about (`Resolution.confirmed`); or
* **a human cleared it** -- an entry here with `cleared_at` set.

## Which statuses can have support withheld, and why not the others

Only `covered` and `partial`. They are the only statuses that make a POSITIVE
claim -- "the client has a control here" -- and a positive claim is the only kind
that can be unsupported.

`unscored` has no claim. `not_applicable` is already outside `addressable`, so
withholding it changes nothing about a number it never entered.

`gap` is the one that needs saying out loud, because an earlier draft of
`analytics._WITHHOLDABLE` included it and that was wrong in the optimistic
direction. A gap is an ABSENCE claim: it asserts that no control was found, and
the evidence for it is precisely the lack of a citation. There is no support to
withhold. Worse, withholding one is not neutral -- `coverage_pct` is
`(covered + 0.5*partial) / (covered + partial + gap)`, so dropping a gap out of
`addressable` **raises** the percentage and deletes a finding. On a 10-covered /
10-gap assessment, flagging the gaps moved the reported number from 50% to 100%.
That is the exact direction 5.1 exists to stop, so `gap` is excluded here and in
`analytics._WITHHOLDABLE` both. See `test_withholding_a_gap_would_raise_the_score`.

## Three kinds of evidence, and why "nothing was cited" is its own case

The first implementation of this module had two: a row was backed by a confirmed
tool, or it was pending. That collapsed two situations a consultant experiences
completely differently, and `test_heatmap_reflects_coverage_after_patches` caught
it -- an admin curating the matrix by hand set ten techniques to `covered` and
the heatmap reported **zero** covered and 0% coverage, with no action available
anywhere in the product that could ever change it.

So the row's citation record answers a question with three answers, not two:

1. **Something was cited and it is confirmed.** A tool sits in one of the three
   lists and no uncleared entry names it. The claim is backed.
2. **Something was cited and it is NOT confirmed.** Either it was INFERRED (an
   entry with a `tool`, awaiting a human) or it was REJECTED (an entry with
   `tool: null`, naming the string the model sent). Both mean evidence was
   offered for this claim and does not stand up -- pending.
3. **Nothing was ever cited.** No entries at all. There is no unconfirmed
   evidence, because there is no evidence. The status stands on whoever assigned
   it, and for a hand-curated row that is a consultant, whose judgement is not an
   AI inference and was never what 5.1 was about.

Everything in case 2 is stored, including the two outcomes that resolve to no
tool name at all -- a REJECTED citation (`reason` one of `rejected_*`, carrying
the string the model sent) and a positive status the model cited NOTHING for
(`reason` `no_citation`, carrying neither). Neither has a tool to record, which
is exactly why they have to be recorded: without them, "the model cited Qradar
and we dropped it" and "the model claimed coverage and named nothing" both store
as `[]` over empty tool lists, which is byte-identical to a consultant's own
hand-curated `covered` -- and that third one must NOT be withheld. Case 3 is
therefore reached only by a row a human authored, or one where every citation
landed cleanly.

That fidelity is what makes the plan's "related defect" enforceable at all: "a
technique can currently read `covered` with EMPTY tool lists ... treat it as in
scope". Both routes to an empty tool list are now distinguishable from having
nothing to cite.

A human clears case 2 the way 5.1 says: by vouching for the entry (`cleared_at`),
by naming a tool that resolves cleanly, or -- through `patch_coverage` -- by
setting the status or the tool lists themselves, which makes them the author of
the claim rather than a reviewer of the model's.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from app.attack.coverage import CoverageStatus

#: Statuses that make a positive claim, and therefore need backing. See the
#: module docstring for why `gap` is not one of them.
CLAIMS_SUPPORT = frozenset({CoverageStatus.COVERED.value, CoverageStatus.PARTIAL.value})

#: Tool-list fields on `AttackCoverage` whose contents are cited capabilities.
TOOL_FIELDS = ("detection_tools", "prevention_tools", "response_tools")

#: `reason` values for an entry that resolved to NO tool. Kept distinct from
#: `ReviewReason` so a reader never has to guess whether an entry names an
#: applied tool: these are exactly the entries whose `tool` is null.
REJECTED_UNKNOWN = "rejected_unknown"
REJECTED_AMBIGUOUS = "rejected_ambiguous"

#: The model assigned a positive status and cited NOTHING -- no tool to resolve,
#: so nothing to reject and nothing to infer. Recorded as its own entry because
#: without one the row is byte-identical to a hand-curated `covered`, and those
#: two must score differently: the consultant is the author of their claim, the
#: model is not the author of this one. This is the plan's related defect in its
#: most literal form -- "a technique can currently read `covered` with EMPTY tool
#: lists".
NO_CITATION = "no_citation"


def _entries(unconfirmed_citations: list | None) -> list[Mapping]:
    """Validate the stored shape, or raise.

    Raises on a malformed entry rather than skipping it. This column is written
    by our own code in exactly two places; an entry that is not an object is a
    bug in a writer, and skipping it would silently turn unconfirmed evidence
    into confirmed evidence -- the failure this whole module exists to end,
    arriving through its own error handling.
    """
    if unconfirmed_citations is None:
        return []
    if not isinstance(unconfirmed_citations, list):
        raise ValueError(
            "unconfirmed_citations must be a list or None, got "
            f"{type(unconfirmed_citations).__name__}"
        )
    out: list[Mapping] = []
    for i, entry in enumerate(unconfirmed_citations):
        if not isinstance(entry, Mapping):
            raise ValueError(f"unconfirmed_citations[{i}] is not an object: {entry!r}")
        tool = entry.get("tool")
        if tool is not None and (not isinstance(tool, str) or not tool.strip()):
            raise ValueError(
                f"unconfirmed_citations[{i}] has a 'tool' that is neither null nor a "
                f"name: {entry!r}"
            )
        out.append(entry)
    return out


def uncleared_tools(unconfirmed_citations: list | None) -> frozenset[str]:
    """Names of APPLIED tools whose citation was inferred and not yet cleared.

    Entries with a null `tool` are rejections -- they applied nothing, so they
    cannot cancel out a tool in the row's lists. They are counted by
    `has_uncleared_evidence` instead.
    """
    return frozenset(
        e["tool"]
        for e in _entries(unconfirmed_citations)
        if e.get("tool") is not None and e.get("cleared_at") is None
    )


def has_uncleared_evidence(unconfirmed_citations: list | None) -> bool:
    """True when SOMETHING was cited for this row and is not confirmed.

    Covers both halves of case 2 in the module docstring: an inference awaiting a
    human, and a citation that resolved to nothing at all.
    """
    return any(e.get("cleared_at") is None for e in _entries(unconfirmed_citations))


def is_pending_review(
    status: str | None,
    unconfirmed_citations: list | None,
    tools: Iterable[str],
) -> bool:
    """True when `status` makes a claim this row's evidence does not yet support.

    `tools` is the union of the row's detection / prevention / response lists.
    """
    if status not in CLAIMS_SUPPORT:
        return False
    # NULL is not `[]`. NULL means the citations were never resolved, so nothing
    # on record says this row's support was ever checked -- and absence of
    # evidence is not evidence of confirmation (migration 0044, D-054's shape).
    if unconfirmed_citations is None:
        return True
    flagged = uncleared_tools(unconfirmed_citations)
    if any(t for t in tools if t not in flagged):
        return False  # case 1: at least one confirmed tool backs the claim
    # Case 2 vs case 3. Nothing confirmed backs the claim either way; what
    # separates them is whether anything was ever OFFERED. Evidence that was
    # offered and did not stand up withholds the claim; a row nobody cited
    # anything for has no unconfirmed evidence to withhold it.
    return has_uncleared_evidence(unconfirmed_citations)


def row_tools(row: object) -> list[str]:
    """The union of a coverage row's three tool lists, order preserved."""
    seen: set[str] = set()
    out: list[str] = []
    for field in TOOL_FIELDS:
        for tool in getattr(row, field, None) or []:
            if isinstance(tool, str) and tool not in seen:
                seen.add(tool)
                out.append(tool)
    return out


def pending_codes(rows: Iterable[object]) -> frozenset[str]:
    """The technique codes `analytics.compute` must withhold, from stored rows."""
    return frozenset(
        row.technique_code
        for row in rows
        if is_pending_review(row.status, row.unconfirmed_citations, row_tools(row))
    )


def confirm_all(unconfirmed_citations: list | None, *, at: object) -> list:
    """Stamp every uncleared entry as vouched for, returning the new list.

    Used when a human takes authorship of a row (`patch_coverage`): they set the
    status or curated the tools themselves, so the model's inferences are no
    longer what the claim rests on.

    Entries are STAMPED, never deleted. "A human looked at this and accepted it"
    is a different state from "nobody ever cited it", and the difference is
    exactly what an auditor asking why a technique counts needs to see. A NULL
    column becomes `[]` -- resolved, nothing outstanding.
    """
    return [
        dict(e) if e.get("cleared_at") is not None else {**e, "cleared_at": at}
        for e in _entries(unconfirmed_citations)
    ]


__all__ = [
    "CLAIMS_SUPPORT",
    "NO_CITATION",
    "REJECTED_AMBIGUOUS",
    "REJECTED_UNKNOWN",
    "TOOL_FIELDS",
    "confirm_all",
    "has_uncleared_evidence",
    "is_pending_review",
    "pending_codes",
    "row_tools",
    "uncleared_tools",
]
