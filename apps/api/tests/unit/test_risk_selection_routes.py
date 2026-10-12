"""RR-1 (for #1122): the generate body, the gate's lists, publish and the
files, through the real routes (design note rev 12, §3, §5, §6, §9.1).

Matrix A, API, every row: its rows are extracted by script from the note's
§2a table (sha256 d17b3aed64128954...), grouped by the client's state so each world is
seeded once and every body of that state is sent to it. Expected messages are
§8's copy, verbatim; never read from `routes/risk.py`'s constants.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.ai.llm import LLMResponse
from tests._attack_rows import first_standalone
from tests.unit.test_risk_per_service import _export_texts, _h, _per_finding
from tests.unit.test_risk_register import (  # noqa: F401  (app_client is a fixture)
    _admin,
    _pdf_text,
    _seed_csf_playbook_at_level,
    _session,
    app_client,
)

pytestmark = pytest.mark.unit

CISA = "cisa_ztmm_2_0"
DOD = "dod_ztra"
CISA_LABEL = "Zero Trust (CISA ZTMM 2.0)"
DOD_LABEL = "Zero Trust (DoD ZT Reference Architecture)"
COPY_5 = {
    "5a": "Choose NIST CSF, Zero Trust, or both. ATT&CK coverage alone is not enough for a register.",
    "5b": "Choose a Zero Trust framework. ATT&CK coverage alone is not enough for a register.",
    "5d": "Include NIST CSF. ATT&CK coverage alone is not enough for a register.",
}
COPY_5C = "Include {label}. ATT&CK coverage alone is not enough for a register."
COPY_6 = "This client has both Zero Trust frameworks. Choose one for this register."
COPY_7A = "{label} cannot be included: this client has not engaged that service."
COPY_7C = "{label} cannot be included: that service has been archived."
COPY_7B = "{title} cannot be included: it has no assessment yet."
COPY_8 = "This register was generated from {list}."
COPY_9A = "{label} was not included in this register."
COPY_9C = (
    "{label} was engaged but had no assessment when this register was generated, so it is "
    "not in this register."
)
COPY_11 = (
    "This register has no usable record of how its services were chosen or which were left out."
)
COPY_19 = (
    "This register has no usable record of how its services were chosen or which were left "
    "out, so it cannot be published. Regenerate it, then publish the new version."
)

#: The service titles the worlds below give, for 7b's `{title}`.
TITLES = {"NIST CSF": "CSF svc", CISA_LABEL: "CISA svc", DOD_LABEL: "DoD svc"}


def _seed_attack(c, h: dict) -> str:
    svc = c.post("/attack/services", headers=h, json={"kind": "attack_coverage", "title": "A"})
    assert svc.status_code in (200, 201), svc.text
    a = c.post(f"/attack/services/{svc.json()['id']}/assessments", headers=h).json()
    cov = first_standalone(a["coverage"])
    r = c.patch(f"/attack/coverage/{cov['id']}", headers=h, json={"status": "gap"})
    assert r.status_code == 200, r.text
    assert c.post(f"/attack/assessments/{a['id']}/approve", headers=h).status_code == 200
    return svc.json()["id"]


def _seed_zt(c, h: dict, kind: str, title: str, *, assessed: bool) -> str:
    svc = c.post("/zt/services", headers=h, json={"kind": kind, "title": title})
    assert svc.status_code in (200, 201), svc.text
    if assessed:
        a = c.post(f"/zt/services/{svc.json()['id']}/assessments", headers=h)
        assert a.status_code in (200, 201), a.text
        ans = a.json()["answers"][0]
        r = c.patch(f"/zt/answers/{ans['id']}", headers=h, json={"maturity_stage": 1})
        assert r.status_code == 200, r.text
        ap = c.post(f"/zt/assessments/{a.json()['id']}/approve", headers=h)
        assert ap.status_code == 200, ap.text
    return svc.json()["id"]


def _seed_csf_unassessed(c, h: dict) -> str:
    svc = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF svc"})
    assert svc.status_code in (200, 201), svc.text
    return svc.json()["id"]


def _world(c, bearer: str, cid: str, csf: str, cisa: str, dod: str) -> dict[str, str]:
    """ATT&CK approved, plus each family in the state the row names."""
    h = _h(bearer, cid)
    ids = {"attack": _seed_attack(c, h)}
    if csf == "eligible":
        _seed_csf_playbook_at_level(c, bearer, cid, level=1)
    elif csf == "no_record":
        ids["csf"] = _seed_csf_unassessed(c, h)
    for state, kind, title, key in (
        (cisa, "zero_trust_cisa", "CISA svc", "cisa"),
        (dod, "zero_trust_dod", "DoD svc", "dod"),
    ):
        if state != "none":
            ids[key] = _seed_zt(c, h, kind, title, assessed=state == "eligible")
    return ids


def _generate(c, provider, bearer: str, cid: str, body: dict | None):
    provider.register("risk_synthesize", _per_finding([]))
    kw = {} if body is None else {"json": body}
    return c.post(f"/risk/clients/{cid}/register/generate", headers=_h(bearer, cid), **kw)


def _body(b_csf: str, b_zt: str) -> dict | None:
    if b_csf in ("(no body)", "any"):
        return None
    zt = None if b_zt == "null" else json_str(b_zt)
    return {"include": {"csf": b_csf == "true", "zero_trust": zt}}


def json_str(cell: str) -> str:
    assert cell.startswith('"') and cell.endswith('"'), cell
    return cell[1:-1]


def _expected_message(copy: str, eligible_zt: list[str]) -> tuple[str, str]:
    """(reason, message) for a 409 row's copy cell."""
    if copy in COPY_5:
        return "risk_selection_needs_csf_or_zt", COPY_5[copy]
    if copy == "5c":
        (label,) = eligible_zt
        return "risk_selection_needs_csf_or_zt", COPY_5C.format(label=label)
    if copy == "6":
        return "risk_selection_zero_trust_ambiguous", COPY_6
    if copy.startswith("7a, "):
        return "risk_selection_not_engaged", COPY_7A.format(label=copy[len("7a, ") :])
    prefix = "7b, the service title ("
    assert copy.startswith(prefix) and copy.endswith(")"), copy
    label = copy[len(prefix) : -1]
    return "risk_selection_no_assessment", COPY_7B.format(title=TITLES[label])


# (client state (CSF, CISA, DoD), [(row, csf, zero_trust, status, copy), ...])
MATRIX_A_API = [
    (
        ("none", "none", "none"),
        [
            ("B1", "any", "any", "409 (existing)", "existing"),
        ],
    ),
    (
        ("none", "none", "no_record"),
        [
            ("B2", "any", "any", "409 (existing)", "existing"),
        ],
    ),
    (
        ("none", "none", "eligible"),
        [
            ("B3", "false", "null", "409", "5c"),
            ("B4", "false", '"cisa_ztmm_2_0"', "409", "7a, Zero Trust (CISA ZTMM 2.0)"),
            ("B5", "false", '"dod_ztra"', "201", "-"),
            ("B6", "true", "null", "409", "7a, NIST CSF"),
            ("B7", "true", '"cisa_ztmm_2_0"', "409", "7a, NIST CSF"),
            ("B8", "true", '"dod_ztra"', "409", "7a, NIST CSF"),
            ("B9", "(no body)", "(no body)", "201", "-"),
        ],
    ),
    (
        ("none", "no_record", "none"),
        [
            ("B10", "any", "any", "409 (existing)", "existing"),
        ],
    ),
    (
        ("none", "no_record", "no_record"),
        [
            ("B11", "any", "any", "409 (existing)", "existing"),
        ],
    ),
    (
        ("none", "no_record", "eligible"),
        [
            ("B12", "false", "null", "409", "5c"),
            (
                "B13",
                "false",
                '"cisa_ztmm_2_0"',
                "409",
                "7b, the service title (Zero Trust (CISA ZTMM 2.0))",
            ),
            ("B14", "false", '"dod_ztra"', "201", "-"),
            ("B15", "true", "null", "409", "7a, NIST CSF"),
            ("B16", "true", '"cisa_ztmm_2_0"', "409", "7a, NIST CSF"),
            ("B17", "true", '"dod_ztra"', "409", "7a, NIST CSF"),
            ("B18", "(no body)", "(no body)", "201", "-"),
        ],
    ),
    (
        ("none", "eligible", "none"),
        [
            ("B19", "false", "null", "409", "5c"),
            ("B20", "false", '"cisa_ztmm_2_0"', "201", "-"),
            ("B21", "false", '"dod_ztra"', "409", "7a, Zero Trust (DoD ZT Reference Architecture)"),
            ("B22", "true", "null", "409", "7a, NIST CSF"),
            ("B23", "true", '"cisa_ztmm_2_0"', "409", "7a, NIST CSF"),
            ("B24", "true", '"dod_ztra"', "409", "7a, NIST CSF"),
            ("B25", "(no body)", "(no body)", "201", "-"),
        ],
    ),
    (
        ("none", "eligible", "no_record"),
        [
            ("B26", "false", "null", "409", "5c"),
            ("B27", "false", '"cisa_ztmm_2_0"', "201", "-"),
            (
                "B28",
                "false",
                '"dod_ztra"',
                "409",
                "7b, the service title (Zero Trust (DoD ZT Reference Architecture))",
            ),
            ("B29", "true", "null", "409", "7a, NIST CSF"),
            ("B30", "true", '"cisa_ztmm_2_0"', "409", "7a, NIST CSF"),
            ("B31", "true", '"dod_ztra"', "409", "7a, NIST CSF"),
            ("B32", "(no body)", "(no body)", "201", "-"),
        ],
    ),
    (
        ("none", "eligible", "eligible"),
        [
            ("B33", "false", "null", "409", "5b"),
            ("B34", "false", '"cisa_ztmm_2_0"', "201", "-"),
            ("B35", "false", '"dod_ztra"', "201", "-"),
            ("B36", "true", "null", "409", "7a, NIST CSF"),
            ("B37", "true", '"cisa_ztmm_2_0"', "409", "7a, NIST CSF"),
            ("B38", "true", '"dod_ztra"', "409", "7a, NIST CSF"),
            ("B39", "(no body)", "(no body)", "409", "6"),
        ],
    ),
    (
        ("no_record", "none", "none"),
        [
            ("B40", "any", "any", "409 (existing)", "existing"),
        ],
    ),
    (
        ("no_record", "none", "no_record"),
        [
            ("B41", "any", "any", "409 (existing)", "existing"),
        ],
    ),
    (
        ("no_record", "none", "eligible"),
        [
            ("B42", "false", "null", "409", "5c"),
            ("B43", "false", '"cisa_ztmm_2_0"', "409", "7a, Zero Trust (CISA ZTMM 2.0)"),
            ("B44", "false", '"dod_ztra"', "201", "-"),
            ("B45", "true", "null", "409", "7b, the service title (NIST CSF)"),
            ("B46", "true", '"cisa_ztmm_2_0"', "409", "7b, the service title (NIST CSF)"),
            ("B47", "true", '"dod_ztra"', "409", "7b, the service title (NIST CSF)"),
            ("B48", "(no body)", "(no body)", "201", "-"),
        ],
    ),
    (
        ("no_record", "no_record", "none"),
        [
            ("B49", "any", "any", "409 (existing)", "existing"),
        ],
    ),
    (
        ("no_record", "no_record", "no_record"),
        [
            ("B50", "any", "any", "409 (existing)", "existing"),
        ],
    ),
    (
        ("no_record", "no_record", "eligible"),
        [
            ("B51", "false", "null", "409", "5c"),
            (
                "B52",
                "false",
                '"cisa_ztmm_2_0"',
                "409",
                "7b, the service title (Zero Trust (CISA ZTMM 2.0))",
            ),
            ("B53", "false", '"dod_ztra"', "201", "-"),
            ("B54", "true", "null", "409", "7b, the service title (NIST CSF)"),
            ("B55", "true", '"cisa_ztmm_2_0"', "409", "7b, the service title (NIST CSF)"),
            ("B56", "true", '"dod_ztra"', "409", "7b, the service title (NIST CSF)"),
            ("B57", "(no body)", "(no body)", "201", "-"),
        ],
    ),
    (
        ("no_record", "eligible", "none"),
        [
            ("B58", "false", "null", "409", "5c"),
            ("B59", "false", '"cisa_ztmm_2_0"', "201", "-"),
            ("B60", "false", '"dod_ztra"', "409", "7a, Zero Trust (DoD ZT Reference Architecture)"),
            ("B61", "true", "null", "409", "7b, the service title (NIST CSF)"),
            ("B62", "true", '"cisa_ztmm_2_0"', "409", "7b, the service title (NIST CSF)"),
            ("B63", "true", '"dod_ztra"', "409", "7b, the service title (NIST CSF)"),
            ("B64", "(no body)", "(no body)", "201", "-"),
        ],
    ),
    (
        ("no_record", "eligible", "no_record"),
        [
            ("B65", "false", "null", "409", "5c"),
            ("B66", "false", '"cisa_ztmm_2_0"', "201", "-"),
            (
                "B67",
                "false",
                '"dod_ztra"',
                "409",
                "7b, the service title (Zero Trust (DoD ZT Reference Architecture))",
            ),
            ("B68", "true", "null", "409", "7b, the service title (NIST CSF)"),
            ("B69", "true", '"cisa_ztmm_2_0"', "409", "7b, the service title (NIST CSF)"),
            ("B70", "true", '"dod_ztra"', "409", "7b, the service title (NIST CSF)"),
            ("B71", "(no body)", "(no body)", "201", "-"),
        ],
    ),
    (
        ("no_record", "eligible", "eligible"),
        [
            ("B72", "false", "null", "409", "5b"),
            ("B73", "false", '"cisa_ztmm_2_0"', "201", "-"),
            ("B74", "false", '"dod_ztra"', "201", "-"),
            ("B75", "true", "null", "409", "7b, the service title (NIST CSF)"),
            ("B76", "true", '"cisa_ztmm_2_0"', "409", "7b, the service title (NIST CSF)"),
            ("B77", "true", '"dod_ztra"', "409", "7b, the service title (NIST CSF)"),
            ("B78", "(no body)", "(no body)", "409", "6"),
        ],
    ),
    (
        ("eligible", "none", "none"),
        [
            ("B79", "false", "null", "409", "5d"),
            ("B80", "false", '"cisa_ztmm_2_0"', "409", "7a, Zero Trust (CISA ZTMM 2.0)"),
            ("B81", "false", '"dod_ztra"', "409", "7a, Zero Trust (DoD ZT Reference Architecture)"),
            ("B82", "true", "null", "201", "-"),
            ("B83", "true", '"cisa_ztmm_2_0"', "409", "7a, Zero Trust (CISA ZTMM 2.0)"),
            ("B84", "true", '"dod_ztra"', "409", "7a, Zero Trust (DoD ZT Reference Architecture)"),
            ("B85", "(no body)", "(no body)", "201", "-"),
        ],
    ),
    (
        ("eligible", "none", "no_record"),
        [
            ("B86", "false", "null", "409", "5d"),
            ("B87", "false", '"cisa_ztmm_2_0"', "409", "7a, Zero Trust (CISA ZTMM 2.0)"),
            (
                "B88",
                "false",
                '"dod_ztra"',
                "409",
                "7b, the service title (Zero Trust (DoD ZT Reference Architecture))",
            ),
            ("B89", "true", "null", "201", "-"),
            ("B90", "true", '"cisa_ztmm_2_0"', "409", "7a, Zero Trust (CISA ZTMM 2.0)"),
            (
                "B91",
                "true",
                '"dod_ztra"',
                "409",
                "7b, the service title (Zero Trust (DoD ZT Reference Architecture))",
            ),
            ("B92", "(no body)", "(no body)", "201", "-"),
        ],
    ),
    (
        ("eligible", "none", "eligible"),
        [
            ("B93", "false", "null", "409", "5a"),
            ("B94", "false", '"cisa_ztmm_2_0"', "409", "7a, Zero Trust (CISA ZTMM 2.0)"),
            ("B95", "false", '"dod_ztra"', "201", "-"),
            ("B96", "true", "null", "201", "-"),
            ("B97", "true", '"cisa_ztmm_2_0"', "409", "7a, Zero Trust (CISA ZTMM 2.0)"),
            ("B98", "true", '"dod_ztra"', "201", "-"),
            ("B99", "(no body)", "(no body)", "201", "-"),
        ],
    ),
    (
        ("eligible", "no_record", "none"),
        [
            ("B100", "false", "null", "409", "5d"),
            (
                "B101",
                "false",
                '"cisa_ztmm_2_0"',
                "409",
                "7b, the service title (Zero Trust (CISA ZTMM 2.0))",
            ),
            (
                "B102",
                "false",
                '"dod_ztra"',
                "409",
                "7a, Zero Trust (DoD ZT Reference Architecture)",
            ),
            ("B103", "true", "null", "201", "-"),
            (
                "B104",
                "true",
                '"cisa_ztmm_2_0"',
                "409",
                "7b, the service title (Zero Trust (CISA ZTMM 2.0))",
            ),
            ("B105", "true", '"dod_ztra"', "409", "7a, Zero Trust (DoD ZT Reference Architecture)"),
            ("B106", "(no body)", "(no body)", "201", "-"),
        ],
    ),
    (
        ("eligible", "no_record", "no_record"),
        [
            ("B107", "false", "null", "409", "5d"),
            (
                "B108",
                "false",
                '"cisa_ztmm_2_0"',
                "409",
                "7b, the service title (Zero Trust (CISA ZTMM 2.0))",
            ),
            (
                "B109",
                "false",
                '"dod_ztra"',
                "409",
                "7b, the service title (Zero Trust (DoD ZT Reference Architecture))",
            ),
            ("B110", "true", "null", "201", "-"),
            (
                "B111",
                "true",
                '"cisa_ztmm_2_0"',
                "409",
                "7b, the service title (Zero Trust (CISA ZTMM 2.0))",
            ),
            (
                "B112",
                "true",
                '"dod_ztra"',
                "409",
                "7b, the service title (Zero Trust (DoD ZT Reference Architecture))",
            ),
            ("B113", "(no body)", "(no body)", "201", "-"),
        ],
    ),
    (
        ("eligible", "no_record", "eligible"),
        [
            ("B114", "false", "null", "409", "5a"),
            (
                "B115",
                "false",
                '"cisa_ztmm_2_0"',
                "409",
                "7b, the service title (Zero Trust (CISA ZTMM 2.0))",
            ),
            ("B116", "false", '"dod_ztra"', "201", "-"),
            ("B117", "true", "null", "201", "-"),
            (
                "B118",
                "true",
                '"cisa_ztmm_2_0"',
                "409",
                "7b, the service title (Zero Trust (CISA ZTMM 2.0))",
            ),
            ("B119", "true", '"dod_ztra"', "201", "-"),
            ("B120", "(no body)", "(no body)", "201", "-"),
        ],
    ),
    (
        ("eligible", "eligible", "none"),
        [
            ("B121", "false", "null", "409", "5a"),
            ("B122", "false", '"cisa_ztmm_2_0"', "201", "-"),
            (
                "B123",
                "false",
                '"dod_ztra"',
                "409",
                "7a, Zero Trust (DoD ZT Reference Architecture)",
            ),
            ("B124", "true", "null", "201", "-"),
            ("B125", "true", '"cisa_ztmm_2_0"', "201", "-"),
            ("B126", "true", '"dod_ztra"', "409", "7a, Zero Trust (DoD ZT Reference Architecture)"),
            ("B127", "(no body)", "(no body)", "201", "-"),
        ],
    ),
    (
        ("eligible", "eligible", "no_record"),
        [
            ("B128", "false", "null", "409", "5a"),
            ("B129", "false", '"cisa_ztmm_2_0"', "201", "-"),
            (
                "B130",
                "false",
                '"dod_ztra"',
                "409",
                "7b, the service title (Zero Trust (DoD ZT Reference Architecture))",
            ),
            ("B131", "true", "null", "201", "-"),
            ("B132", "true", '"cisa_ztmm_2_0"', "201", "-"),
            (
                "B133",
                "true",
                '"dod_ztra"',
                "409",
                "7b, the service title (Zero Trust (DoD ZT Reference Architecture))",
            ),
            ("B134", "(no body)", "(no body)", "201", "-"),
        ],
    ),
    (
        ("eligible", "eligible", "eligible"),
        [
            ("B135", "false", "null", "409", "5a"),
            ("B136", "false", '"cisa_ztmm_2_0"', "201", "-"),
            ("B137", "false", '"dod_ztra"', "201", "-"),
            ("B138", "true", "null", "201", "-"),
            ("B139", "true", '"cisa_ztmm_2_0"', "201", "-"),
            ("B140", "true", '"dod_ztra"', "201", "-"),
            ("B141", "(no body)", "(no body)", "409", "6"),
        ],
    ),
]


def test_matrix_a_api_is_whole() -> None:
    ids = [row[0] for _state, rows in MATRIX_A_API for row in rows]
    assert ids == [f"B{i}" for i in range(1, 142)]


@pytest.mark.parametrize("state, rows", MATRIX_A_API, ids=["-".join(s) for s, _ in MATRIX_A_API])
def test_matrix_a_api(state, rows, app_client) -> None:  # noqa: F811
    c, provider = app_client
    bearer, cid = _admin(c)
    csf, cisa, dod = state
    _world(c, bearer, cid, csf, cisa, dod)
    eligible_zt = [
        label for st, label in ((cisa, CISA_LABEL), (dod, DOD_LABEL)) if st == "eligible"
    ]
    for rid, b_csf, b_zt, status, copy in rows:
        r = _generate(c, provider, bearer, cid, _body(b_csf, b_zt))
        if status == "409 (existing)":
            # LOCKED: refused before any selection is read, by the existing gate.
            assert r.status_code == 409, (rid, r.text)
            assert not r.json()["error"]["reason"].startswith("risk_selection_"), (rid, r.text)
            continue
        if status == "201":
            assert r.status_code == 201, (rid, r.text)
            assert r.json()["selection_recorded"] is True, (rid, r.json())
            continue
        assert status == "409", rid
        assert r.status_code == 409, (rid, r.text)
        reason, message = _expected_message(copy, eligible_zt)
        err = r.json()["error"]
        assert (err["reason"], err["message"]) == (reason, message), rid


# ---------------------------------------------------------------------------
# Refusals outside the matrix
# ---------------------------------------------------------------------------


def test_7c_names_a_framework_whose_only_service_is_archived(app_client) -> None:  # noqa: F811
    c, provider = app_client
    bearer, cid = _admin(c)
    _world(c, bearer, cid, "eligible", "none", "none")
    h = _h(bearer, cid)
    dod = _seed_zt(c, h, "zero_trust_dod", "DoD svc", assessed=True)
    gone = c.delete(f"/admin/services/{dod}", headers=h)
    assert gone.status_code == 204, gone.text
    r = _generate(c, provider, bearer, cid, {"include": {"csf": True, "zero_trust": DOD}})
    assert r.status_code == 409, r.text
    assert (r.json()["error"]["reason"], r.json()["error"]["message"]) == (
        "risk_selection_not_engaged",
        COPY_7C.format(label=DOD_LABEL),
    )
    # And 7a for a framework never engaged, beside it.
    r = _generate(c, provider, bearer, cid, {"include": {"csf": True, "zero_trust": CISA}})
    assert r.json()["error"]["message"] == COPY_7A.format(label=CISA_LABEL), r.text


def test_the_duplicate_refusal_precedes_and_ignores_the_selection(app_client) -> None:  # noqa: F811
    c, provider = app_client
    bearer, cid = _admin(c)
    _world(c, bearer, cid, "none", "eligible", "none")
    _seed_zt(c, _h(bearer, cid), "zero_trust_cisa", "CISA svc 2", assessed=True)
    # A body that would itself be refused (7a): the duplicate refusal wins.
    r = _generate(c, provider, bearer, cid, {"include": {"csf": True, "zero_trust": DOD}})
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "risk_register_duplicate_inputs", r.text


@pytest.mark.parametrize(
    "body",
    [
        {"include": {"csf": True}},
        {"include": {"csf": True, "zero_trust": "zt"}},
        {"include": {"csf": "yes", "zero_trust": None}},
        {"include": {"csf": 1, "zero_trust": None}},
        {"include": {"csf": True, "zero_trust": None, "attack": False}},
        {"csf": True, "zero_trust": None},
    ],
)
def test_a_malformed_body_is_refused_typed_and_generates_nothing(
    body, app_client  # noqa: F811
) -> None:
    c, provider = app_client
    bearer, cid = _admin(c)
    _world(c, bearer, cid, "eligible", "eligible", "none")
    r = _generate(c, provider, bearer, cid, body)
    assert r.status_code == 422, r.text
    latest = c.get(f"/risk/clients/{cid}/register/latest", headers=_h(bearer, cid))
    assert latest.status_code in (200, 404), latest.text
    assert latest.status_code == 404 or latest.json() is None, latest.text


# ---------------------------------------------------------------------------
# The record, the gate and publish
# ---------------------------------------------------------------------------


def _provenance(cid: str) -> dict:
    from app.models.risk_register import RiskRegister

    with _session() as s:
        reg = (
            s.execute(
                select(RiskRegister)
                .where(RiskRegister.client_id == uuid.UUID(cid))
                .order_by(RiskRegister.version.desc())
            )
            .scalars()
            .first()
        )
        return dict(reg.provenance)


def test_generate_records_the_selection_and_narrows_current_inputs(
    app_client,  # noqa: F811
) -> None:
    c, provider = app_client
    bearer, cid = _admin(c)
    ids = _world(c, bearer, cid, "eligible", "eligible", "eligible")
    h = _h(bearer, cid)
    r = _generate(c, provider, bearer, cid, {"include": {"csf": False, "zero_trust": CISA}})
    assert r.status_code == 201, r.text
    prov = _provenance(cid)
    sel = prov["selection"]
    assert sel["version"] == 1
    assert [(x["kind"], x["framework"]) for x in sel["included"]] == [("zt", CISA)]
    assert sorted((x["kind"], x["framework"]) for x in sel["deselected"]) == [
        ("csf", None),
        ("zt", DOD),
    ]
    assert sel["ineligible"] == []
    deselected_ids = {x["service_id"] for x in sel["deselected"]}
    assert not deselected_ids & {x["service_id"] for x in prov["current_inputs"]}
    assert ids["attack"] in {x["service_id"] for x in prov["current_inputs"]}
    assert {x["kind"] for x in prov["inputs"]} == {"attack", "zt"}
    g = c.get(f"/risk/clients/{cid}/gate", headers=h).json()
    by_kind = {(row["kind"], row.get("qualifier")): row["in_register"] for row in g["inputs"]}
    assert by_kind[("csf", None)] == "deselected", g["inputs"]
    assert by_kind[("zt", "DoD ZT Reference Architecture")] == "deselected", g["inputs"]
    assert by_kind[("zt", "CISA ZTMM 2.0")] == "input", g["inputs"]


def test_the_gate_lists_selectable_services_with_labels_and_no_tech_debt(
    app_client,  # noqa: F811
) -> None:
    c, _provider = app_client
    bearer, cid = _admin(c)
    _world(c, bearer, cid, "no_record", "eligible", "no_record")
    h = _h(bearer, cid)
    td = c.post("/tech-debt/services", headers=h, json={"kind": "tech_debt", "title": "TD"})
    assert td.status_code in (200, 201), td.text
    g = c.get(f"/risk/clients/{cid}/gate", headers=h)
    assert g.status_code == 200, g.text
    body = g.json()
    assert [(r["kind"], r["label"]) for r in body["eligible"]] == [
        ("attack", "ATT&CK coverage"),
        ("zt", CISA_LABEL),
    ]
    assert [(r["kind"], r["label"]) for r in body["ineligible"]] == [
        ("csf", "NIST CSF"),
        ("zt", DOD_LABEL),
    ]
    assert all(r["kind"] != "tech_debt" for r in body["eligible"] + body["ineligible"])


def test_a_second_attack_service_with_no_record_is_listed_nowhere_and_blocks_publish(
    app_client,  # noqa: F811
) -> None:
    c, provider = app_client
    bearer, cid = _admin(c)
    _world(c, bearer, cid, "none", "eligible", "none")
    h = _h(bearer, cid)
    a2 = c.post("/attack/services", headers=h, json={"kind": "attack_coverage", "title": "A2"})
    assert a2.status_code in (200, 201), a2.text
    g = c.get(f"/risk/clients/{cid}/gate", headers=h).json()
    assert g["unlocked"] is True
    listed = {r["service_id"] for r in g["eligible"] + g["ineligible"]}
    assert a2.json()["id"] not in listed
    provider.register_static(
        "risk_synthesize",
        LLMResponse(
            '{"entries": [{"title": "R", "description": "d", "axis": "detection", '
            '"source": null, "source_id": null, "linked_techniques": [], '
            '"linked_controls": [], "likelihood": "high", "impact": "major", '
            '"recommended_action": "remediate", "rationale": "r"}]}'
        ),
    )
    r = c.post(f"/risk/clients/{cid}/register/generate", headers=h)
    assert r.status_code == 201, r.text
    pub = c.post(f"/risk/clients/{cid}/register/publish", headers=h)
    assert pub.status_code == 409, pub.text
    blockers = pub.json()["error"]["blockers"]
    assert {"input": "attack", "reason": "not_started", "status": None} in blockers, blockers


def _set_provenance(cid: str, **over) -> None:
    from app.models.risk_register import RiskRegister

    with _session() as s:
        reg = (
            s.execute(
                select(RiskRegister)
                .where(RiskRegister.client_id == uuid.UUID(cid))
                .order_by(RiskRegister.version.desc())
            )
            .scalars()
            .first()
        )
        prov = dict(reg.provenance)
        for k, v in over.items():
            if v is _DROP:
                prov.pop(k, None)
            else:
                prov[k] = v
        reg.provenance = prov
        s.commit()


_DROP = object()


@pytest.mark.parametrize(
    "name, over",
    [
        ("key absent", {"selection": _DROP}),
        ("null", {"selection": None}),
        ("invalid", {"selection": {"version": 1, "included": "x"}}),
        ("current_inputs None (§4 check 5)", {"current_inputs": None}),
        ("current_inputs not a list (§4 check 5)", {"current_inputs": "attack"}),
    ],
)
def test_no_usable_selection_refuses_publish_with_copy_19_and_prints_copy_11(
    name, over, app_client  # noqa: F811
) -> None:
    c, provider = app_client
    bearer, cid = _admin(c)
    _world(c, bearer, cid, "eligible", "none", "none")
    h = _h(bearer, cid)
    assert _generate(c, provider, bearer, cid, None).status_code == 201
    _set_provenance(cid, **over)
    pub = c.post(f"/risk/clients/{cid}/register/publish", headers=h)
    assert pub.status_code == 409, (name, pub.text)
    err = pub.json()["error"]
    assert err["blockers"] == [{"input": "register", "reason": "not_recorded", "status": None}]
    assert err["message"] == COPY_19, name
    latest = c.get(f"/risk/clients/{cid}/register/latest", headers=h)
    assert latest.status_code == 200, (name, latest.text)
    assert latest.json()["selection_recorded"] is False, name
    assert latest.json()["covered_inputs"] == [], name
    ex = c.post(f"/risk/clients/{cid}/register/export", headers=h)
    if ex.status_code == 200:
        for kind, text in _export_texts(c, bearer, cid).items():
            flat = " ".join(text.split())
            assert COPY_11 in flat, (name, kind)
            assert "This register was generated from" not in flat, (name, kind)
    else:
        # Export's own #240 guard refuses some of these shapes first; what
        # matters here is that nothing 500s.
        assert ex.status_code == 409, (name, ex.text)


# ---------------------------------------------------------------------------
# What the files and the screens say
# ---------------------------------------------------------------------------


def _lines_in_every_file(c, bearer, cid, *lines: str) -> None:
    for kind, text in _export_texts(c, bearer, cid).items():
        flat = " ".join(text.split())
        for line in lines:
            assert line in flat, (kind, line)


def test_a6_names_the_cisa_scored_coverage_row_in_every_file(app_client) -> None:  # noqa: F811
    """A6/A8 shape: CISA eligible, DoD engaged with no assessment. The bare
    `zt` scope key is named like copy 8 and 9c beside it (§6.2)."""
    c, provider = app_client
    bearer, cid = _admin(c)
    _world(c, bearer, cid, "none", "eligible", "no_record")
    h = _h(bearer, cid)
    r = _generate(c, provider, bearer, cid, None)
    assert r.status_code == 201, r.text
    body = c.get(f"/risk/clients/{cid}/register/latest", headers=h).json()
    assert body["covered_inputs"] == ["ATT&CK coverage", CISA_LABEL]
    assert body["ineligible_inputs"] == [DOD_LABEL]
    scope = {s["service"]: s["label"] for s in body["excluded_unscored_links"]}
    assert scope.get("zt") == CISA_LABEL, scope
    assert [t["label"] for t in body["targets"]] == [CISA_LABEL]
    _lines_in_every_file(
        c,
        bearer,
        cid,
        COPY_8.format(list=f"ATT&CK coverage and {CISA_LABEL}"),
        COPY_9C.format(label=DOD_LABEL),
    )
    texts = _export_texts(c, bearer, cid)
    assert CISA_LABEL in texts["xlsx"]
    for kind, text in texts.items():
        assert "Zero Trust:" not in " ".join(text.split()), kind


@pytest.mark.parametrize(
    "name, state, body, targets, lines",
    [
        (
            "one ZT input and nothing else ZT: unnamed",
            ("none", "eligible", "none"),
            None,
            ["Zero Trust"],
            [COPY_8.format(list="ATT&CK coverage and Zero Trust")],
        ),
        (
            "one ZT input, the other framework deselected: named",
            ("none", "eligible", "eligible"),
            {"include": {"csf": False, "zero_trust": CISA}},
            [CISA_LABEL],
            [
                COPY_8.format(list=f"ATT&CK coverage and {CISA_LABEL}"),
                COPY_9A.format(label=DOD_LABEL),
            ],
        ),
        (
            "one ZT input, the other ineligible: named",
            ("none", "eligible", "no_record"),
            None,
            [CISA_LABEL],
            [
                COPY_8.format(list=f"ATT&CK coverage and {CISA_LABEL}"),
                COPY_9C.format(label=DOD_LABEL),
            ],
        ),
        (
            "CSF plus one ZT, the other deselected: NIST CSF, then the named ZT",
            ("eligible", "eligible", "eligible"),
            {"include": {"csf": True, "zero_trust": DOD}},
            ["NIST CSF", DOD_LABEL],
            [
                COPY_8.format(list=f"ATT&CK coverage, NIST CSF and {DOD_LABEL}"),
                COPY_9A.format(label=CISA_LABEL),
            ],
        ),
    ],
)
def test_the_server_label_table(
    name, state, body, targets, lines, app_client  # noqa: F811
) -> None:
    c, provider = app_client
    bearer, cid = _admin(c)
    _world(c, bearer, cid, *state)
    r = _generate(c, provider, bearer, cid, body)
    assert r.status_code == 201, (name, r.text)
    latest = c.get(f"/risk/clients/{cid}/register/latest", headers=_h(bearer, cid)).json()
    assert [t["label"] for t in latest["targets"]] == targets, name
    _lines_in_every_file(c, bearer, cid, *lines)
