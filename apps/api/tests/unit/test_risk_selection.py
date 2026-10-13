"""RR-1 (for #1122): the selection record, read by ONE reader, and what it
decides -- publish's blockers and the Inputs panel's `in_register` (Matrix B),
and the scored-coverage and target labels (design note rev 12, §4, §5, §6.2).

Expected strings are the design note's §8 copy and its approved label table,
never read from `exporters.py`'s constants. Matrix B's rows are extracted by
script from the note's §2a table (sha256 d17b3aed64128954...), not written by hand.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.risk import inputs as risk_inputs
from app.risk.exporters import (
    build_context,
    render_docx,
    render_pdf,
    render_xlsx,
    scope_display_label,
    selection_context,
    selection_lines,
    target_row_label,
)
from app.risk.inputs import InputRecord, publish_blockers
from app.risk.selection import (
    SELECTION_NOT_RECORDED,
    SELECTION_UNREADABLE,
    Selection,
    SelectionRow,
    selection_of,
    selection_roles,
)

pytestmark = pytest.mark.unit

COPY_11 = (
    "This register has no usable record of how its services were chosen or which " "were left out."
)
CISA = "cisa_ztmm_2_0"
DOD = "dod_ztra"
CSF_ID = "00000000-0000-4000-8000-0000000000c5"
CISA_ID = "00000000-0000-4000-8000-00000000c15a"
DOD_ID = "00000000-0000-4000-8000-000000000d0d"
ATTACK_ID = "00000000-0000-4000-8000-0000000000a7"


def _sel(included=(), deselected=(), ineligible=()) -> dict:
    return {
        "version": 1,
        "included": list(included),
        "deselected": list(deselected),
        "ineligible": list(ineligible),
    }


def _row(kind: str, sid: str, framework: str | None = None) -> dict:
    return {"kind": kind, "service_id": sid, "framework": framework}


def _prov(**over) -> dict:
    """A post-RR-1 provenance: ATT&CK and CSF in, CISA deselected."""
    base = {
        "inputs": [
            {"kind": "attack", "service_id": ATTACK_ID, "framework": None},
            {"kind": "csf", "service_id": CSF_ID, "framework": None},
        ],
        "current_inputs": [
            {"kind": "attack", "service_id": ATTACK_ID},
            {"kind": "csf", "service_id": CSF_ID},
        ],
        "selection": _sel(included=[_row("csf", CSF_ID)], deselected=[_row("zt", CISA_ID, CISA)]),
    }
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# selection_of: the one reader (§4)
# ---------------------------------------------------------------------------


def test_a_valid_selection_parses() -> None:
    sel = selection_of(_prov())
    assert isinstance(sel, Selection)
    assert sel.included == (SelectionRow("csf", CSF_ID, None),)
    assert sel.deselected == (SelectionRow("zt", CISA_ID, CISA),)
    assert sel.ineligible == ()


def test_an_absent_key_is_not_recorded_and_null_is_unreadable() -> None:
    prov = _prov()
    del prov["selection"]
    assert selection_of(prov) is SELECTION_NOT_RECORDED
    assert selection_of(None) is SELECTION_NOT_RECORDED
    assert selection_of(_prov(selection=None)) is SELECTION_UNREADABLE


@pytest.mark.parametrize(
    "name, over",
    [
        ("not an object", {"selection": ["x"]}),
        ("wrong version", {"selection": {**_sel(included=[_row("csf", CSF_ID)]), "version": 2}}),
        # Check 5: `current_inputs` unreadable.
        ("current_inputs None", {"current_inputs": None}),
        ("current_inputs not a list", {"current_inputs": {"attack": ATTACK_ID}}),
        ("current_inputs row without id", {"current_inputs": [{"kind": "attack"}]}),
        # Check 3: a row unreadable.
        ("row not an object", {"selection": _sel(included=["csf"])}),
        ("row without id", {"selection": _sel(included=[{"kind": "csf", "framework": None}])}),
        ("csf row with a framework", {"selection": _sel(included=[_row("csf", CSF_ID, CISA)])}),
        (
            "zt row without a framework",
            {"selection": _sel(included=[_row("csf", CSF_ID)], deselected=[_row("zt", CISA_ID)])},
        ),
        ("a list missing", {"selection": {"version": 1, "included": [_row("csf", CSF_ID)]}}),
        # Check 4: only CSF and ZT are named.
        (
            "attack in ineligible",
            {"selection": _sel(included=[_row("csf", CSF_ID)], ineligible=[_row("attack", "a2")])},
        ),
        (
            "tech_debt in ineligible",
            {
                "selection": _sel(
                    included=[_row("csf", CSF_ID)], ineligible=[_row("tech_debt", "td")]
                )
            },
        ),
        # Check 1: disjoint, and no id twice in one list.
        (
            "an input also deselected",
            {"selection": _sel(included=[_row("csf", CSF_ID)], deselected=[_row("csf", CSF_ID)])},
        ),
        (
            "an input also ineligible",
            {"selection": _sel(included=[_row("csf", CSF_ID)], ineligible=[_row("csf", CSF_ID)])},
        ),
        (
            "deselected and ineligible",
            {
                "selection": _sel(
                    included=[_row("csf", CSF_ID)],
                    deselected=[_row("zt", CISA_ID, CISA)],
                    ineligible=[_row("zt", CISA_ID, CISA)],
                )
            },
        ),
        (
            "an id twice in deselected",
            {
                "selection": _sel(
                    included=[_row("csf", CSF_ID)],
                    deselected=[_row("zt", CISA_ID, CISA), _row("zt", CISA_ID, CISA)],
                )
            },
        ),
        # Check 2: `included` equals the CSF and ZT ids of `inputs`.
        (
            "included not an input",
            {"selection": _sel(included=[_row("csf", CSF_ID), _row("zt", CISA_ID, CISA)])},
        ),
        ("an input not included", {"selection": _sel()}),
        ("inputs unreadable", {"inputs": None}),
    ],
)
def test_each_failing_shape_is_unreadable(name: str, over: dict) -> None:
    assert selection_of(_prov(**over)) is SELECTION_UNREADABLE, name


@pytest.mark.parametrize("current", [None, "attack", 3])
def test_check_5_runs_before_check_1_so_nothing_raises(current: object) -> None:
    """§4's order: an intact `selection` beside an unreadable `current_inputs`
    is UNREADABLE, never a TypeError from check 1's set arithmetic."""
    prov = _prov(
        current_inputs=current,
        selection=_sel(included=[_row("csf", CSF_ID)], deselected=[_row("zt", CISA_ID, CISA)]),
    )
    assert selection_of(prov) is SELECTION_UNREADABLE


# ---------------------------------------------------------------------------
# publish_blockers: the selection is required, and the sentinels refuse first
# ---------------------------------------------------------------------------


def test_publish_blockers_without_a_selection_is_a_type_error() -> None:
    with pytest.raises(TypeError):
        publish_blockers(None, uuid.uuid4(), [], [])  # type: ignore[call-arg]


@pytest.mark.parametrize("sentinel", [SELECTION_NOT_RECORDED, SELECTION_UNREADABLE])
def test_a_sentinel_refuses_the_whole_register_before_any_lookup(sentinel) -> None:
    # `db=None`: a lookup would raise, so reaching one fails this test.
    blockers = publish_blockers(None, uuid.uuid4(), [], [], selection=sentinel)
    assert [(b.kind, b.reason) for b in blockers] == [("register", "not_recorded")]


# ---------------------------------------------------------------------------
# Matrix B, every row: publish's column and the panel's `in_register` column,
# both from `selection_roles`
# ---------------------------------------------------------------------------

# (id, kind, framework, role at generate, engaged now, record now, vs generate,
#  publish reason or None, in_register or None for "no panel row")
MATRIX_B = [
    ("C1", "attack", None, "included", True, "none", "n/a", "not_started", "input"),
    ("C2", "attack", None, "included", True, "not RELEASED", "n/a", "not_released", "input"),
    (
        "C3",
        "attack",
        None,
        "included",
        True,
        "RELEASED",
        "same record, released at generate",
        None,
        "input",
    ),
    (
        "C4",
        "attack",
        None,
        "included",
        True,
        "RELEASED",
        "moved, or not released at generate",
        "changed",
        "input",
    ),
    ("C5", "attack", None, "included", False, "n/a", "n/a", "changed", None),
    ("C6", "attack", None, "unrecorded", True, "none", "n/a", "not_started", "input"),
    ("C7", "attack", None, "unrecorded", True, "not RELEASED", "n/a", "not_released", "input"),
    ("C8", "attack", None, "unrecorded", True, "RELEASED", "n/a", "changed", "input"),
    ("C9", "attack", None, "unrecorded", False, "n/a", "n/a", None, None),
    ("C10", "attack", None, "unnamed", True, "none", "n/a", "not_started", "input"),
    ("C11", "attack", None, "unnamed", True, "not RELEASED", "n/a", "not_released", "input"),
    ("C12", "attack", None, "unnamed", True, "RELEASED", "n/a", "changed", "input"),
    ("C13", "attack", None, "unnamed", False, "n/a", "n/a", None, None),
    ("C14", "csf", None, "included", True, "none", "n/a", "not_started", "input"),
    ("C15", "csf", None, "included", True, "not RELEASED", "n/a", "not_released", "input"),
    (
        "C16",
        "csf",
        None,
        "included",
        True,
        "RELEASED",
        "same record, released at generate",
        None,
        "input",
    ),
    (
        "C17",
        "csf",
        None,
        "included",
        True,
        "RELEASED",
        "same record, Playbook edited since generate",
        "changed",
        "input",
    ),
    (
        "C18",
        "csf",
        None,
        "included",
        True,
        "RELEASED",
        "moved, or not released at generate",
        "changed",
        "input",
    ),
    ("C19", "csf", None, "included", False, "n/a", "n/a", "changed", None),
    ("C20", "csf", None, "deselected", True, "any", "n/a", None, "deselected"),
    ("C21", "csf", None, "deselected", False, "any", "n/a", None, None),
    ("C22", "csf", None, "ineligible", True, "none", "n/a", None, "ineligible"),
    ("C23", "csf", None, "ineligible", True, "not RELEASED", "n/a", "not_released", "input"),
    ("C24", "csf", None, "ineligible", True, "RELEASED", "n/a", "changed", "input"),
    ("C25", "csf", None, "ineligible", False, "n/a", "n/a", None, None),
    ("C26", "csf", None, "unnamed", True, "none", "n/a", "not_started", "input"),
    ("C27", "csf", None, "unnamed", True, "not RELEASED", "n/a", "not_released", "input"),
    ("C28", "csf", None, "unnamed", True, "RELEASED", "n/a", "changed", "input"),
    ("C29", "csf", None, "unnamed", False, "n/a", "n/a", None, None),
    ("C30", "zt", "cisa_ztmm_2_0", "included", True, "none", "n/a", "not_started", "input"),
    (
        "C31",
        "zt",
        "cisa_ztmm_2_0",
        "included",
        True,
        "not RELEASED",
        "n/a",
        "not_released",
        "input",
    ),
    (
        "C32",
        "zt",
        "cisa_ztmm_2_0",
        "included",
        True,
        "RELEASED",
        "same record, released at generate",
        None,
        "input",
    ),
    (
        "C33",
        "zt",
        "cisa_ztmm_2_0",
        "included",
        True,
        "RELEASED",
        "moved, or not released at generate",
        "changed",
        "input",
    ),
    ("C34", "zt", "cisa_ztmm_2_0", "included", False, "n/a", "n/a", "changed", None),
    ("C35", "zt", "cisa_ztmm_2_0", "deselected", True, "any", "n/a", None, "deselected"),
    ("C36", "zt", "cisa_ztmm_2_0", "deselected", False, "any", "n/a", None, None),
    ("C37", "zt", "cisa_ztmm_2_0", "ineligible", True, "none", "n/a", None, "ineligible"),
    (
        "C38",
        "zt",
        "cisa_ztmm_2_0",
        "ineligible",
        True,
        "not RELEASED",
        "n/a",
        "not_released",
        "input",
    ),
    ("C39", "zt", "cisa_ztmm_2_0", "ineligible", True, "RELEASED", "n/a", "changed", "input"),
    ("C40", "zt", "cisa_ztmm_2_0", "ineligible", False, "n/a", "n/a", None, None),
    ("C41", "zt", "cisa_ztmm_2_0", "unnamed", True, "none", "n/a", "not_started", "input"),
    ("C42", "zt", "cisa_ztmm_2_0", "unnamed", True, "not RELEASED", "n/a", "not_released", "input"),
    ("C43", "zt", "cisa_ztmm_2_0", "unnamed", True, "RELEASED", "n/a", "changed", "input"),
    ("C44", "zt", "cisa_ztmm_2_0", "unnamed", False, "n/a", "n/a", None, None),
    ("C45", "zt", "dod_ztra", "included", True, "none", "n/a", "not_started", "input"),
    ("C46", "zt", "dod_ztra", "included", True, "not RELEASED", "n/a", "not_released", "input"),
    (
        "C47",
        "zt",
        "dod_ztra",
        "included",
        True,
        "RELEASED",
        "same record, released at generate",
        None,
        "input",
    ),
    (
        "C48",
        "zt",
        "dod_ztra",
        "included",
        True,
        "RELEASED",
        "moved, or not released at generate",
        "changed",
        "input",
    ),
    ("C49", "zt", "dod_ztra", "included", False, "n/a", "n/a", "changed", None),
    ("C50", "zt", "dod_ztra", "deselected", True, "any", "n/a", None, "deselected"),
    ("C51", "zt", "dod_ztra", "deselected", False, "any", "n/a", None, None),
    ("C52", "zt", "dod_ztra", "ineligible", True, "none", "n/a", None, "ineligible"),
    ("C53", "zt", "dod_ztra", "ineligible", True, "not RELEASED", "n/a", "not_released", "input"),
    ("C54", "zt", "dod_ztra", "ineligible", True, "RELEASED", "n/a", "changed", "input"),
    ("C55", "zt", "dod_ztra", "ineligible", False, "n/a", "n/a", None, None),
    ("C56", "zt", "dod_ztra", "unnamed", True, "none", "n/a", "not_started", "input"),
    ("C57", "zt", "dod_ztra", "unnamed", True, "not RELEASED", "n/a", "not_released", "input"),
    ("C58", "zt", "dod_ztra", "unnamed", True, "RELEASED", "n/a", "changed", "input"),
    ("C59", "zt", "dod_ztra", "unnamed", False, "n/a", "n/a", None, None),
    ("C60", "tech_debt", None, "provenance-only", True, "none", "n/a", "not_started", "input"),
    (
        "C61",
        "tech_debt",
        None,
        "provenance-only",
        True,
        "not RELEASED",
        "n/a",
        "not_released",
        "input",
    ),
    (
        "C62",
        "tech_debt",
        None,
        "provenance-only",
        True,
        "RELEASED",
        "same record, released at generate",
        None,
        "input",
    ),
    (
        "C63",
        "tech_debt",
        None,
        "provenance-only",
        True,
        "RELEASED",
        "moved, or not released at generate",
        "changed",
        "input",
    ),
    ("C64", "tech_debt", None, "provenance-only", False, "n/a", "n/a", "changed", None),
    ("C65", "tech_debt", None, "unrecorded", True, "none", "n/a", "not_started", "input"),
    ("C66", "tech_debt", None, "unrecorded", True, "not RELEASED", "n/a", "not_released", "input"),
    ("C67", "tech_debt", None, "unrecorded", True, "RELEASED", "n/a", "changed", "input"),
    ("C68", "tech_debt", None, "unrecorded", False, "n/a", "n/a", None, None),
    ("C69", "tech_debt", None, "unnamed", True, "none", "n/a", "not_started", "input"),
    ("C70", "tech_debt", None, "unnamed", True, "not RELEASED", "n/a", "not_released", "input"),
    ("C71", "tech_debt", None, "unnamed", True, "RELEASED", "n/a", "changed", "input"),
    ("C72", "tech_debt", None, "unnamed", False, "n/a", "n/a", None, None),
]


def _world(row):
    """Build the register and the client's state a Matrix B row names, for ONE
    service. Returns (selection, recorded, synthesized, engaged, now)."""
    _id, kind, framework, role, engaged_now, record, vs, _pub, _reg = row
    sid = str(uuid.uuid5(uuid.NAMESPACE_URL, _id))
    sel_row = SelectionRow(kind, sid, framework)
    included = deselected = ineligible = ()
    recorded: list[dict] = []
    synthesized: list[dict] = []
    if role in ("included", "provenance-only"):
        was = {
            "kind": kind,
            "service_id": sid,
            "record_id": "R1",
            "version": 1,
            "status": "released",
        }
        if vs == "moved, or not released at generate":
            was["record_id"] = "R0"
        if kind == "csf":
            was["playbook_fingerprint"] = (
                "fp-old" if vs == "same record, Playbook edited since generate" else "fp"
            )
        recorded.append(was)
        if role == "included":
            synthesized.append({"kind": kind, "service_id": sid, "framework": framework})
            if kind in ("csf", "zt"):
                included = (sel_row,)
    elif role == "deselected":
        deselected = (sel_row,)
    elif role == "ineligible":
        ineligible = (sel_row,)
    selection = Selection(included=included, deselected=deselected, ineligible=ineligible)
    svc = SimpleNamespace(id=uuid.UUID(sid))
    engaged = [(kind, svc)] if engaged_now else []
    now: list[InputRecord] = []
    if engaged_now and record in ("not RELEASED", "RELEASED", "any"):
        status = "approved" if record == "not RELEASED" else "released"
        now.append(InputRecord(kind, sid, "R1", 1, status, "fp" if kind == "csf" else None))
    return selection, recorded, synthesized, engaged, now, sid


def test_matrix_b_is_whole() -> None:
    assert [r[0] for r in MATRIX_B] == [f"C{i}" for i in range(1, 73)]


@pytest.mark.parametrize("row", MATRIX_B, ids=[r[0] for r in MATRIX_B])
def test_matrix_b_publish_column(row, monkeypatch) -> None:
    selection, recorded, synthesized, engaged, now, _sid = _world(row)
    monkeypatch.setattr(risk_inputs, "engaged_services", lambda db, cid: engaged)
    monkeypatch.setattr(risk_inputs, "current_inputs", lambda db, cid: now)
    blockers = publish_blockers(None, uuid.uuid4(), recorded, synthesized, selection=selection)
    expected = [] if row[7] is None else [(row[1], row[7])]
    assert [(b.kind, b.reason) for b in blockers] == expected


@pytest.mark.parametrize(
    "row", [r for r in MATRIX_B if r[8] is not None], ids=[r[0] for r in MATRIX_B if r[8]]
)
def test_matrix_b_in_register_column(row, monkeypatch) -> None:
    from app.routes import risk as risk_routes

    selection, recorded, synthesized, engaged, now, sid = _world(row)
    reg = SimpleNamespace(
        provenance={
            "inputs": synthesized,
            "current_inputs": recorded,
            "selection": selection.as_json(),
        }
    )
    # The record round-trips through the one reader, as the route reads it.
    assert selection_of(reg.provenance) == selection, row[0]
    monkeypatch.setattr(risk_routes, "_latest_register", lambda db, cid: reg)
    current = {(r.kind, r.service_id): r for r in now}
    out = risk_routes._in_register(None, uuid.uuid4(), engaged, current)
    assert out[(row[1], sid)] == row[8]


def test_selection_roles_names_every_engaged_service() -> None:
    sel = Selection(
        included=(SelectionRow("csf", "c", None),),
        deselected=(SelectionRow("zt", "z1", CISA),),
        ineligible=(SelectionRow("zt", "z2", DOD),),
    )
    roles = selection_roles(
        sel,
        {("attack", "a"), ("csf", "c"), ("tech_debt", "t")},
        [
            ("attack", "a"),
            ("attack", "a2"),
            ("csf", "c"),
            ("csf", "c2"),
            ("zt", "z1"),
            ("zt", "z2"),
            ("tech_debt", "t"),
            ("tech_debt", "t2"),
        ],
    )
    assert {k: (r.name, r.framework) for k, r in roles.items()} == {
        ("attack", "a"): ("included", None),
        ("attack", "a2"): ("unrecorded", None),
        ("csf", "c"): ("included", None),
        ("csf", "c2"): ("unnamed", None),
        ("zt", "z1"): ("deselected", CISA),
        ("zt", "z2"): ("ineligible", DOD),
        ("tech_debt", "t"): ("provenance-only", None),
        ("tech_debt", "t2"): ("unrecorded", None),
    }


# ---------------------------------------------------------------------------
# scope_display_label (§6.2): the key shapes, the cases deleted with
# `apps/web/src/lib/risk/labels.test.ts`, and each fallback with its log
# ---------------------------------------------------------------------------


def _zt_prov(*zt_inputs: dict, deselected=(), ineligible=()) -> dict:
    inputs = [{"kind": "attack", "service_id": ATTACK_ID, "framework": None}, *zt_inputs]
    return {
        "inputs": inputs,
        "current_inputs": [{"kind": i["kind"], "service_id": i["service_id"]} for i in inputs],
        "selection": _sel(
            included=[_row("zt", i["service_id"], i.get("framework")) for i in zt_inputs],
            deselected=list(deselected),
            ineligible=list(ineligible),
        ),
    }


ONE_CISA = {"kind": "zt", "service_id": CISA_ID, "framework": CISA}
ONE_DOD = {"kind": "zt", "service_id": DOD_ID, "framework": DOD}

# The cases `labels.test.ts` held (the web's `scopeLabel`, deleted by RR-1),
# with the strings that file pinned, which the Python labeller printed. A
# register naming one ZT service and nothing else ZT: the bare key is unnamed.
_LABELS_TEST_CASES = [
    ("csf", "NIST CSF"),
    ("zt", "Zero Trust"),
    ("attack", "ATT&CK coverage"),
    ("zt:cisa_ztmm_2_0", "Zero Trust (CISA ZTMM 2.0)"),
    ("zt:dod_ztra", "Zero Trust (DoD ZT Reference Architecture)"),
    ("zt:unknown", "zt:unknown"),
    ("zt:dod_ztra:x", "zt:dod_ztra:x"),
    ("constructor", "constructor"),
    ("zt:constructor", "zt:constructor"),
]


@pytest.mark.parametrize("key, label", _LABELS_TEST_CASES)
def test_the_deleted_web_labels_cases(key: str, label: str) -> None:
    assert scope_display_label(key, _zt_prov(ONE_CISA)) == label


@pytest.mark.parametrize(
    "name, prov, label",
    [
        ("one ZT, nothing else ZT", _zt_prov(ONE_CISA), "Zero Trust"),
        (
            "one ZT, the other deselected",
            _zt_prov(ONE_CISA, deselected=[_row("zt", DOD_ID, DOD)]),
            "Zero Trust (CISA ZTMM 2.0)",
        ),
        (
            "one ZT, the other ineligible (A8)",
            _zt_prov(ONE_CISA, ineligible=[_row("zt", DOD_ID, DOD)]),
            "Zero Trust (CISA ZTMM 2.0)",
        ),
        (
            "DoD in, CISA deselected",
            _zt_prov(ONE_DOD, deselected=[_row("zt", CISA_ID, CISA)]),
            "Zero Trust (DoD ZT Reference Architecture)",
        ),
    ],
)
def test_the_bare_zt_key_follows_the_naming_predicate(name, prov, label) -> None:
    assert scope_display_label("zt", prov) == label, name


@pytest.mark.parametrize(
    "reason, prov",
    [
        ("selection_unreadable", {**_zt_prov(ONE_CISA), "selection": None}),
        (
            "selection_not_recorded",
            {k: v for k, v in _zt_prov(ONE_CISA).items() if k != "selection"},
        ),
        ("no_zt_input", _prov()),
        # Two ZT inputs: a pre-RR-1 shape, which `selection_of` refuses first
        # unless the selection names both; this one does.
        ("several_zt_inputs", _zt_prov(ONE_CISA, ONE_DOD)),
    ],
)
def test_each_fallback_prints_the_bare_label_and_says_why(reason, prov, capsys) -> None:
    assert scope_display_label("zt", prov) == "Zero Trust"
    out = capsys.readouterr().out
    assert "risk.scope_label.zt_unresolved" in out, out
    assert reason in out, out


def test_a_zt_input_with_no_framework_falls_back_and_says_why(capsys) -> None:
    prov = _zt_prov(ONE_CISA)
    prov["inputs"][1] = {"kind": "zt", "service_id": CISA_ID}  # no framework key
    assert scope_display_label("zt", prov) == "Zero Trust"
    out = capsys.readouterr().out
    assert "risk.scope_label.zt_unresolved" in out and "zt_input_without_framework" in out, out


# ---------------------------------------------------------------------------
# Target row labels: the naming cases deleted from `baseline.test.ts`
# ---------------------------------------------------------------------------


def _legacy(*inputs: dict) -> dict:
    """A pre-RR-1 register: readable `inputs`, no `selection`."""
    return {"inputs": list(inputs), "current_inputs": []}


@pytest.mark.parametrize(
    "name, prov, rows",
    [
        # baseline.test.ts "one ZT (DoD, default): the framework is not named"
        ("one ZT unnamed", _legacy(ONE_DOD), [("zt", DOD, "Zero Trust")]),
        # "CISA (client 4) plus DoD (default): each framework is named"
        (
            "CISA plus DoD named",
            _legacy(ONE_CISA, ONE_DOD),
            [
                ("zt", CISA, "Zero Trust (CISA ZTMM 2.0)"),
                ("zt", DOD, "Zero Trust (DoD ZT Reference Architecture)"),
            ],
        ),
        # "CSF plus CISA plus DoD: the CSF line, then the two ZT lines"
        (
            "CSF plus CISA plus DoD",
            _legacy({"kind": "csf", "service_id": CSF_ID, "framework": None}, ONE_CISA, ONE_DOD),
            [
                ("csf", None, "NIST CSF"),
                ("zt", CISA, "Zero Trust (CISA ZTMM 2.0)"),
                ("zt", DOD, "Zero Trust (DoD ZT Reference Architecture)"),
            ],
        ),
        # RR-1: one ZT row, named because the register mentions two ZT services.
        (
            "CSF plus one ZT, the other deselected",
            _prov(
                inputs=[
                    {"kind": "attack", "service_id": ATTACK_ID, "framework": None},
                    {"kind": "csf", "service_id": CSF_ID, "framework": None},
                    ONE_DOD,
                ],
                current_inputs=[
                    {"kind": "attack", "service_id": ATTACK_ID},
                    {"kind": "csf", "service_id": CSF_ID},
                    {"kind": "zt", "service_id": DOD_ID},
                ],
                selection=_sel(
                    included=[_row("csf", CSF_ID), _row("zt", DOD_ID, DOD)],
                    deselected=[_row("zt", CISA_ID, CISA)],
                ),
            ),
            [("csf", None, "NIST CSF"), ("zt", DOD, "Zero Trust (DoD ZT Reference Architecture)")],
        ),
    ],
)
def test_target_row_labels(name, prov, rows) -> None:
    for kind, framework, label in rows:
        assert target_row_label(kind, framework, prov) == label, name


# ---------------------------------------------------------------------------
# The files: copy 11 by default, copy 8 and 9a from a recorded selection
# ---------------------------------------------------------------------------


def _texts(ctx) -> dict[str, str]:
    import io

    from docx import Document
    from openpyxl import load_workbook

    from tests.unit.test_risk_register import _pdf_text

    wb = load_workbook(io.BytesIO(render_xlsx(ctx)))
    xlsx = "\n".join(
        str(v) for ws in wb.worksheets for row in ws.iter_rows(values_only=True) for v in row if v
    )
    doc = Document(io.BytesIO(render_docx(ctx)))
    docx = "\n".join(
        [p.text for p in doc.paragraphs]
        + [cell.text for t in doc.tables for row in t.rows for cell in row.cells]
    )
    return {"pdf": " ".join(_pdf_text(render_pdf(ctx)).split()), "docx": docx, "xlsx": xlsx}


def test_build_context_without_a_disclosure_prints_copy_11_only() -> None:
    texts = _texts(build_context(client_legal_name="Atlas", version=1, entries=[]))
    for kind, text in texts.items():
        assert COPY_11 in " ".join(text.split()), kind
        assert "This register was generated from" not in text, kind
        assert "was not included in this register" not in text, kind


def test_a_recorded_selection_prints_copy_8_and_9a_in_every_file() -> None:
    # One ZT service is mentioned (the deselected CISA), so §6.2's predicate
    # leaves it unnamed, as copy 8 and the target lines would.
    d = selection_context(_prov())
    assert selection_lines(d) == [
        "This register was generated from ATT&CK coverage and NIST CSF.",
        "Zero Trust was not included in this register.",
    ]
    texts = _texts(build_context(client_legal_name="Atlas", version=1, entries=[], disclosure=d))
    for kind, text in texts.items():
        flat = " ".join(text.split())
        assert "This register was generated from ATT&CK coverage and NIST CSF." in flat, kind
        assert "Zero Trust was not included in this register." in flat, kind
        assert COPY_11 not in flat, kind
