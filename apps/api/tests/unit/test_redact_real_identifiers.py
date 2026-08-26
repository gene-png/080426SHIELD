"""Every real identifier in the shipped catalogs must survive the redactor.

WHY THIS EXISTS, and why it is not more truth-table cells.

`redact_for_ai` is the single LLM egress path, so every ATT&CK technique, CSF
subcategory and Zero Trust capability code in the product passes through it on
its way to the model -- hundreds of them, on every run of three services. A rule
that eats one corrupts the model's input silently and, worse, records a
successful redaction over text containing nothing to redact.

The truth tables could not catch this and did not. They stood at 376 cells and
0% unrelated while `T1003.001` egressed as `T[PHONE]`, because the tables
contain `Techniques T1078, T1110 and T1566 apply.` and no SUB-technique
anywhere. Nobody thought of one. That is the enumeration limit sitting one level
above the tables themselves: a hand-written corpus contains what its author
imagined, and this whole family was outside it.

The fix is the same move as USPS Pub 28 for designators and as the old-rule
oracle for the phone rewrite -- **use the published enumeration instead of
listing what you thought of**. These catalogs ARE the enumeration: they are
what the product ships, so a code that exists in the product is a code in this
test, by construction rather than by recall.

WHAT IT HAS ALREADY CAUGHT. Two defects, both branch-introduced, both
client-reaching, and neither visible to any truth-table cell:

  B10  `T1003.001` -> `T[PHONE]`, `{'phone': 1}`
       440 of the 633 ATT&CK ids are sub-techniques. `1003.001` is seven digits
       in two groups with one of exactly three, satisfying both phone
       validators. The parent `T1003` survives, which is precisely why every
       existing row passed.

  B11  `GV.RM-01` -> `GV.[ADDRESS]`, `{'address': 1}`
       All seven CSF Risk Management Strategy subcategories. `RM` is `Rm`
       (Room), a Pub 28 designator added to the facility branch by #139 on this
       branch, and `-` is a valid designator separator. `main` has no facility
       keywords at all, so this was introduced by the fix for a different
       defect.

Both were found by running the catalogs, not by adding cells. B10 surfaced first
through a risk-register fixture that happened to contain a sub-technique -- a
coincidence, not a method.
"""

from __future__ import annotations

import pytest

from app.ai.redact import redact_for_ai
from app.attack.catalog import TECHNIQUES
from app.csf.catalog import CATEGORIES, SUBCATEGORIES
from app.zt.catalog import CISA_CAPABILITIES, DOD_CAPABILITIES

# Derived from the catalogs themselves. A code that ships is a code that is
# tested; there is no second list to keep in sync, which is the property a
# hand-written corpus cannot have.
ATTACK_IDS = sorted({t.id for t in TECHNIQUES})
CSF_CODES = sorted({s.code for s in SUBCATEGORIES} | {c.code for c in CATEGORIES})
ZT_CODES = sorted({c.code for c in CISA_CAPABILITIES} | {c.code for c in DOD_CAPABILITIES})

ALL_IDENTIFIERS = [
    *(("attack", c) for c in ATTACK_IDS),
    *(("csf", c) for c in CSF_CODES),
    *(("zt", c) for c in ZT_CODES),
]

# CONTEXTS, and this is not decoration.
#
# An identifier tested ALONE cannot reach five of the module's ten passes:
# `_CITY_STATE_ZIP` and `_STREET_PAT` need whitespace-separated words in front,
# `_RE_CAGE` needs its keyword upstream, the signature rule needs a preceding
# opener line, and the name/org rules need hints. So the lone-token corpus that
# found B10 and B11 was structurally incapable of finding B12 -- the defect that
# eats `Plugin ID 19506`, which needs `Plugin ID ` in FRONT of the number.
#
# WHAT THIS DOES NOT BUY, measured rather than assumed. An earlier draft of
# this comment claimed the third template would have caught B12 -- the
# city/state/ZIP rule eating `Plugin ID 19506`. It would not, and reverting B12
# leaves every cell here GREEN. `_CITY_STATE_ZIP` needs a bare five-digit run,
# and NO shipped identifier has one: 0 of 848 codes contain one. The contexts
# reach five more passes; they cannot manufacture a token shape the catalogs do
# not contain.
#
# That is the coverage boundary of this whole file in one sentence: it proves
# the redactor does not corrupt what SHIELD SHIPS. Vocabulary arriving at
# runtime -- scanner plugin ids, client capability names, vendor products --
# is unbounded and absent here, and B12 lived in exactly that gap.
CONTEXTS = [
    ("alone", "{code}"),
    ("mid-sentence", "Technique {code} was observed during the review."),
    ("after a label", "Control ID {code} applies."),
]

IN_CONTEXT = [
    (service, code, ctx_id, template.format(code=code))
    for service, code in ALL_IDENTIFIERS
    for ctx_id, template in CONTEXTS
]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("service", "code", "ctx", "text"),
    IN_CONTEXT,
    ids=[f"{s}:{c}:{x}" for s, c, x, _t in IN_CONTEXT],
)
def test_every_shipped_identifier_survives_redaction(
    service: str, code: str, ctx: str, text: str
) -> None:
    """A catalog identifier is not PII and must reach the model byte-for-byte.

    Asserted in three CONTEXTS, because five of the ten passes cannot fire on a
    lone token and the lone-token corpus therefore certified half the module.
    """
    cleaned, counts = redact_for_ai(text, mode="strict")
    assert cleaned == text, (
        f"{service} identifier {code!r} was corrupted to {cleaned!r} in the "
        f"{ctx!r} context, and the ledger recorded {dict(counts)} over text "
        "that contains nothing to redact"
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("service", "code", "ctx", "text"),
    IN_CONTEXT,
    ids=[f"{s}:{c}:{x}" for s, c, x, _t in IN_CONTEXT],
)
def test_no_identifier_records_a_removal(service: str, code: str, ctx: str, text: str) -> None:
    """The audit half. A rule that fires here writes a false ledger entry.

    Separate from the assertion above because the two fail for different
    reasons and a reader needs to know which: text corrupted, or an accounting
    lie about text that was not.
    """
    _cleaned, counts = redact_for_ai(text, mode="strict")
    assert not counts, (
        f"{service} identifier {code!r} recorded removals {dict(counts)} in the " f"{ctx!r} context"
    )


@pytest.mark.unit
def test_the_corpus_is_the_whole_catalog_and_not_a_sample() -> None:
    """Guards the derivation itself.

    If someone replaces the comprehensions above with a hand-picked list, or a
    catalog import silently returns nothing, the parametrised tests still pass
    -- vacuously, over an empty or truncated corpus. That is this repo's
    standing shape: a checker whose "nothing to complain about" and "I had
    nothing to look at" share an outcome.

    The floors are deliberately below today's counts (633/128/87) so ordinary
    catalog growth does not fail them, and far above zero so truncation does.
    """
    assert len(ATTACK_IDS) >= 600, f"ATT&CK catalog collapsed to {len(ATTACK_IDS)} ids"
    assert len(CSF_CODES) >= 100, f"CSF catalog collapsed to {len(CSF_CODES)} codes"
    assert len(ZT_CODES) >= 80, f"ZT catalog collapsed to {len(ZT_CODES)} codes"

    # The sub-technique family is the one B10 lived in. If the catalog ever
    # stopped carrying sub-techniques this corpus would look healthy and cover
    # nothing of what actually broke.
    subs = [c for c in ATTACK_IDS if "." in c]
    assert len(subs) >= 400, f"only {len(subs)} sub-technique ids -- B10's family is the risk"
