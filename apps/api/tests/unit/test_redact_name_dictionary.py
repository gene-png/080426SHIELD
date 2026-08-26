"""The name dictionary must not destroy ordinary words (B13).

`_redact_names` replaces every case-insensitive occurrence of every hint with
`[NAME]`. That makes the dictionary's CONTENTS a security-boundary decision:
one ordinary word in it corrupts that word throughout every payload the tenant
ever sends, on the single egress path, for all five services.

Live on `main`, not branch-introduced -- the only one of item 10's open defects
that is. The seeded Atlas login is `client@atlas.example`, so the deployed
product turns

    "The client has no MFA on the client VPN"

into two `[NAME]` placeholders on every Tech Debt extraction for that tenant.

Three halves, and they fail differently:

  (a) generic mailboxes become dictionary entries      -- fixed upstream
  (b) an org legally named `Core` destroys the noun     -- RESIDUAL, see below
  (c) hint order decides whether a surname is published -- fixed in the redactor
"""

from __future__ import annotations

import pytest

from app.ai.redact import redact_for_ai
from app.tech_debt.extract import _looks_like_an_account_name

# Shared mailboxes every real deployment has. NOT the fixture for a deny-list --
# the code carries no list of these; they are here to show the STRUCTURAL test
# rejects them, so a mailbox nobody thought of is rejected too.
SHARED_MAILBOXES = [
    "security",
    "admin",
    "it",
    "ops",
    "info",
    "support",
    "helpdesk",
    "hr",
    "qa",
    "client",
    "billing",
    "noreply",
    "sales",
    "legal",
]

# Generated account identifiers: a separator, a digit, or mixed case.
PERSONAL_ACCOUNTS = [
    "dana.whitfield",
    "d_whitfield",
    "dana-whitfield",
    "D.Whitfield",
    "jdoe2",
    "a.b",
]


@pytest.mark.unit
@pytest.mark.parametrize("local", SHARED_MAILBOXES)
def test_a_shared_mailbox_never_becomes_a_name_hint(local: str) -> None:
    """A mailbox is a word, and a word in the dictionary destroys the word."""
    assert not _looks_like_an_account_name(local), (
        f"{local!r} would be added to the name dictionary and every occurrence "
        f"of the word {local!r} in every payload would become [NAME]"
    )


@pytest.mark.unit
@pytest.mark.parametrize("local", PERSONAL_ACCOUNTS)
def test_a_generated_account_identifier_is_still_a_name_hint(local: str) -> None:
    """The other half. Without it the fix is a one-way ratchet that leaks names.

    A test that only asserted rejection would pass against
    `return False` -- which would silently disable name redaction entirely,
    trading an over-match for a leak. That is the worse direction.
    """
    assert _looks_like_an_account_name(local)


@pytest.mark.unit
def test_the_seeded_login_is_the_case_that_proves_it() -> None:
    """`client@atlas.example` is in `seed_demo.py` and in CLAUDE.md's dev logins.

    Named explicitly because this is not a hypothetical: it is the shipped demo
    tenant, so the defect was reproducible on any developer's machine at any
    point in the last several months.
    """
    assert not _looks_like_an_account_name("client")


@pytest.mark.unit
def test_ordinary_prose_survives_a_dictionary_built_from_that_login() -> None:
    """End to end through the real redactor, with the hint list the bug produced."""
    text = "The client has no MFA on the client VPN"
    cleaned, counts = redact_for_ai(text, mode="strict", name_hints=("client",))
    # The hint is honoured when explicitly supplied -- this asserts the SHAPE of
    # the damage, so that if the upstream filter is ever removed the size of the
    # regression is on record.
    assert counts.get("name") == 2
    assert cleaned == "The [NAME] has no MFA on the [NAME] VPN"


@pytest.mark.unit
@pytest.mark.parametrize(
    "hints",
    [("Dana", "Dana Whitfield"), ("Dana Whitfield", "Dana")],
    ids=["short-first", "long-first"],
)
def test_a_partial_name_match_never_publishes_the_surname(hints: tuple[str, ...]) -> None:
    """(c) Python alternation is first-match-wins, not longest-match-wins.

    Parametrised over BOTH orders on purpose: with only one order the test
    passes for whichever order the fix happens to produce, and the defect was
    that the order came from database row ordering. A single-order test would
    prove nothing about the case that bit.

    `[NAME] Whitfield` is worse than no redaction at all -- it publishes the
    surname under an output that reads as a completed redaction. Same shape as
    `Suite B 201` -> `[ADDRESS] 201`.
    """
    cleaned, _counts = redact_for_ai(
        "Signed by Dana Whitfield, CISO", mode="strict", name_hints=hints
    )

    assert "Whitfield" not in cleaned, f"surname published: {cleaned!r}"
    assert cleaned == "Signed by [NAME], CISO"


@pytest.mark.unit
def test_the_org_name_residual_is_recorded_not_fixed() -> None:
    """(b) A tenant legally named `Core` still has the common noun destroyed.

    Pinned as a KNOWN residual rather than left undocumented. There is no
    structural tell to test -- an organisation really can be called Core, Delta
    or Sentinel -- so this needs a product decision at intake rather than a
    predicate, and an unstated exemption reads as an oversight to whoever finds
    it next.

    If this test starts failing, the residual was closed and this cell should
    become a LEAVE assertion instead.
    """
    cleaned, counts = redact_for_ai(
        "The core control set is core to our rollout", mode="strict", client_org_name="Core"
    )

    assert counts.get("client_org") == 2
    assert cleaned == "The [CLIENT] control set is [CLIENT] to our rollout"
