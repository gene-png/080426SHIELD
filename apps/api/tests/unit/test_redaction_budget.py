"""The redaction budget, the copy each surface shows, and parity (for #552).

* The budget is per PAYLOAD and fails CLOSED: the real matcher, over the #546
  worst case, is stopped and nothing reaches the provider.
* The Tech Debt run says the approved sentence verbatim, with {N} from the
  setting; any other surface says a sentence that names no capability list.
* Isolation changes WHERE redaction runs and nothing about WHAT it produces:
  the child's output equals the in-process redactor's over the #130 classes.
"""

from __future__ import annotations

import pytest
from sqlalchemy import insert

from app.ai.redact import redact_payload
from tests import _isolation_targets as targets
from tests import _redaction_world as rw
from tests._redaction_world import _world  # noqa: F401 - the `world` fixture

#: Approved copy (#736 6094262391), quoted, not built: the test is the spec.
_TECH_DEBT_BUDGET_COPY = (
    "Checking this inventory for people's names took longer than the 0.5-second "
    "limit, so the check was stopped and nothing was sent to the AI provider. "
    "No capability list was created."
)


def _add_crafted_tenant_users(w: dict, n: int) -> None:
    """The #546 worst case: `n` display names sharing a 240-dash prefix, plus
    one that breaks the prefix at its first character, all in one anchor group
    (non-word start, word end). Inserted directly: registering 1024 users over
    HTTP would hash 1024 passwords and test nothing more."""
    from app.models.user import User, UserRole

    rows = [
        {
            "email": f"u{i:04d}@example.com",
            "password_hash": "x",
            "role": UserRole.CLIENT,
            "display_name": "-" * 240 + f" n{i:04d}",
            "client_id": w["tenant_id"],
        }
        for i in range(n)
    ]
    rows.append(
        {
            "email": "breaker@example.com",
            "password_hash": "x",
            "role": UserRole.CLIENT,
            "display_name": "+" + "-" * 239 + " zz",
            "client_id": w["tenant_id"],
        }
    )
    with w["Session"]() as db:
        db.execute(insert(User), rows)
        db.commit()


@pytest.mark.unit
def test_real_matcher_over_budget_fails_closed_with_the_approved_copy(world) -> None:
    """THE MARGIN, so this cannot flake on a fast or slow machine. #546 measured
    the worst case at 427-556 ns per sharing hint per character (api image,
    Python 3.12.13; H = 1024 measured 438-520). This payload is 1024 sharing
    hints over 27 cells of 9 700 characters, 261 900 characters, so about
    1024 x 261 900 x 438 ns = 117 s at the measured FLOOR. The budget is
    0.5 s: a margin of over 230x. A machine would have to be 230x faster than
    the api image for the redaction to finish inside the budget, and the hang
    guard is 60 s, so a missing budget fails in a minute rather than passing in
    two."""
    _add_crafted_tenant_users(world, 1024)
    cell = "-" * 9_700
    csv_text = "Application,Description\n" + "".join(f"App {i},{cell}\n" for i in range(27))
    svc_id, artifact_id = rw.service_and_artifact(world, csv_text)

    run = rw.post_within(rw.HANG_GUARD_S, lambda: rw.extract(world, svc_id, artifact_id))

    assert run["status"] == "failed", run
    assert run["error_reason"] == "redaction_budget_exceeded", run
    assert run["error_message"] == _TECH_DEBT_BUDGET_COPY, run["error_message"]
    assert run["charged_likely"] is False, run
    # The copy's last sentence, asserted as a FACT about the database.
    assert rw.lists_for(world, svc_id) == 0, "the copy says no capability list was created"
    assert world["sent"] == [], "the provider was called after the budget ran out"
    assert rw.llm_rows(world) == 0, "an llm_calls row was written for a call never made"


#: The neutral sentence the single egress raises (#736 6094274195, approved in
#: 6094620397), with {N} from the setting, here 0.5.
_NEUTRAL_BUDGET_COPY = (
    "Checking this payload for people's names took longer than the 0.5-second "
    "limit, so the check was stopped and nothing was sent to the AI provider."
)


@pytest.mark.unit
def test_a_csf_run_over_budget_says_the_neutral_sentence(world, monkeypatch) -> None:
    """The budget sits at the single egress, shared by every service. Only
    Tech Debt makes a capability list, so only Tech Debt may say none was
    created. A CSF Run-AI over budget says the neutral sentence, verbatim, and
    nothing about a capability list."""
    import app.ai.isolation as isolation

    monkeypatch.setattr(isolation, "_TARGET", targets.spin_forever)
    svc_id = rw.csf_service(world)

    run = rw.post_within(rw.HANG_GUARD_S, lambda: rw.csf_run(world, svc_id))

    assert run["status"] == "failed", run
    assert run["error_reason"] == "redaction_budget_exceeded", run
    assert run["error_message"] == _NEUTRAL_BUDGET_COPY, run["error_message"]
    assert "capability list" not in run["error_message"].lower()
    assert world["sent"] == [], "the provider was called after the budget ran out"


@pytest.mark.unit
def test_the_preview_over_budget_answers_a_typed_503(world, monkeypatch) -> None:
    """The preview redacts inside the REQUEST, not in a run, so the refusal is
    the response: a typed 503 with the neutral sentence, never a 500 or a raw
    dump, and its one-call place is given back."""
    import app.ai.isolation as isolation

    monkeypatch.setattr(isolation, "_TARGET", targets.spin_forever)
    c, h = world["c"], world["h"]
    svc_id = rw.csf_service(world)

    r = rw.post_within(
        rw.HANG_GUARD_S, lambda: c.post("/ai/preview", headers=h, json={"service_id": svc_id})
    )

    assert r.status_code == 503, r.text
    error = r.json()["error"]
    assert error["reason"] == "redaction_budget_exceeded", error
    assert error["message"] == _NEUTRAL_BUDGET_COPY, error
    assert isolation.places_in_use() == 0, "the preview's one-call place was not given back"


# ---------------------------------------------------------------------------
# Parity over the #130 classes
# ---------------------------------------------------------------------------

#: One row per class a hand-written corpus structurally misses (CLAUDE.md, the
#: #130 bullet), beside the ordinary cases each rule exists for. Every value
#: shape a payload carries is here too: nested dicts, lists, a tuple, and
#: non-string scalars, so a transport that changed a TYPE would show.
_CORPUS: dict = {
    "ordinary": [
        "Owner Dana Whitfield, dana.whitfield@acme.example, 555-123-4567",
        "Acme Holdings, Inc. runs the VPN; SSN 123-45-6789, EIN 12-3456789",
        "CAGE 1ABC2 under contract W91QUZ-21-D-0001",
        "Ship to 1600 Pennsylvania Ave NW, Suite 201, Washington, DC 20500",
    ],
    "malformed": [
        "Dana  Whitfield",
        "Dana\u00a0Whitfield",
        "(Dana Whitfield)",
        "Dana\nWhitfield",
        "dana.whitfield@",
        "555-12",
        "",
        "   ",
        "\u2028Dana Whitfield\u2029",
    ],
    "name_and_version": [
        "Dana Whitfield 2.0",
        "Windows Server 2019 build 17763.1",
        "T1003.001 and T1078",
        "GV.RM-01 and PR.AA-05",
        "Unit 42 and CrowdStrike Falcon 7.11",
    ],
    "non_us": [
        "+44 20 7946 0958",
        "Müller owns the firewall",
        "10 Downing Street, London SW1A 2AA",
        "Rue de Rivoli, 75001 Paris",
        "Tel. 030 1234567, Berlin",
    ],
    "already_redacted": [
        "[NAME] owns [EMAIL] and [PHONE]",
        "[CLIENT] in depth",
        "Suite [ADDRESS] for [NAME] Whitfield",
    ],
    "shapes": {
        "nested": {"owner": "Dana Whitfield", "count": 3, "flag": True, "none": None},
        "tuple": ("Dana Whitfield", 2.5),
        "list": [["dana.whitfield@acme.example"], {"k": "Acme Holdings, Inc."}],
    },
}

_HINTS = ("Dana Whitfield", "dana.whitfield", "Müller")
_ORG = "Acme Holdings, Inc."


@pytest.mark.unit
@pytest.mark.parametrize("mode", ["strict", "standard"])
def test_child_output_equals_in_process_output(world, mode) -> None:
    """The oracle is the in-process `redact_payload` -- the code being MOVED,
    not a reimplementation of it, so this pins "where changed, what did not".
    A difference is a defect in the transport, whichever side looks right."""
    from app.ai.isolation import redact_payload_isolated

    expected = redact_payload(_CORPUS, mode=mode, client_org_name=_ORG, name_hints=_HINTS)
    got = redact_payload_isolated(_CORPUS, mode=mode, client_org_name=_ORG, name_hints=_HINTS)

    assert got == expected
    assert type(got[0]["shapes"]["tuple"]) is tuple, "a tuple came back as another type"
    assert got[1], "the corpus redacted nothing, so parity was checked over nothing"


# ---------------------------------------------------------------------------
# The time settings are finite and bounded, or the api does not start
# (#1042 review, finding 3)
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("setting", ["BUDGET_SECONDS", "SLOT_WAIT_SECONDS"])
@pytest.mark.parametrize("value", ["inf", "1e12"])
def test_startup_refuses_a_redaction_time_that_is_infinite_or_huge(
    monkeypatch, setting: str, value: str
) -> None:
    """Accepted, either value reaches `poll` or `Event.wait` and raises
    OverflowError on the first redaction, past every typed path. Refused at
    startup instead."""
    from pydantic import ValidationError

    from app.config import get_settings
    from app.main import create_app

    monkeypatch.setenv(f"SHIELD_REDACTION_{setting}", value)
    get_settings.cache_clear()
    try:
        with pytest.raises(ValidationError, match=f"shield_redaction_{setting.lower()}"):
            create_app()
    finally:
        monkeypatch.delenv(f"SHIELD_REDACTION_{setting}")
        get_settings.cache_clear()
