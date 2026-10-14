"""A Risk Register RR-1 can no longer generate: two Zero Trust frameworks in one.

Registers generated before RR-1 (#1122) can hold both CISA and DoD Zero Trust.
RR-1's generate draws on one framework per register, but those older
registers still exist, are still exported and published, and every surface
must still render them. This builds that older shape from two REAL generates,
one per framework, and merges the second into the pre-RR-1 form: both Zero
Trust rows in `inputs`, `current_inputs` and `targets`, and no `selection` key,
so publish applies the pre-RR-1 rule (`selection_of` -> not recorded).

Every value is one a generate wrote. Only the merge is hand-written, and it
fails loudly when either run did not record exactly one Zero Trust source of
the framework it was asked for, so it cannot quietly build some other shape.
Entries are picked by their recorded `kind` and `framework`, never by scope
key: a scope key is an id that is "never parsed or rendered"
(`routes/risk.py::_targets_record`).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.risk_register import RiskRegister
from app.risk.zt_capped import CAPPED_TARGET_KEY

CISA = "cisa_ztmm_2_0"
DOD = "dod_ztra"


def _one(rows: list[dict], what: str) -> dict:
    assert len(rows) == 1, f"expected exactly one {what}, got {rows!r}"
    return rows[0]


def _zt_input(prov: dict, framework: str) -> dict:
    return _one(
        [r for r in prov["inputs"] if r["kind"] == "zt" and r["framework"] == framework],
        f"Zero Trust {framework} input",
    )


def _zt_target_key(prov: dict, framework: str) -> str:
    keys = [
        k
        for k, v in prov["targets"].items()
        if v["kind"] == "zt" and v["framework"] == framework
    ]
    assert len(keys) == 1, f"expected one {framework} target, got {prov['targets']!r}"
    return keys[0]


def merge_into_pre_rr1_two_zt(session_factory, cid: str) -> None:
    """Rewrite the client's LATEST register (generated for DoD) into the
    pre-RR-1 two-framework shape, taking CISA's rows from the register before
    it (generated for CISA)."""
    with session_factory() as s:
        regs = (
            s.execute(
                select(RiskRegister)
                .where(RiskRegister.client_id == uuid.UUID(cid))
                .order_by(RiskRegister.version)
            )
            .scalars()
            .all()
        )
        assert len(regs) >= 2, "generate once for CISA, then once for DoD"
        cisa_reg, dod_reg = regs[-2], regs[-1]
        p1, p2 = dict(cisa_reg.provenance), dict(dod_reg.provenance)

        cisa_in, dod_in = _zt_input(p1, CISA), _zt_input(p2, DOD)
        merged = dict(p2)
        merged.pop("selection")
        merged["inputs"] = [*p2["inputs"], cisa_in]
        merged["current_inputs"] = [
            *p2["current_inputs"],
            _one(
                [r for r in p1["current_inputs"] if r["service_id"] == cisa_in["service_id"]],
                "CISA current input",
            ),
        ]
        cisa_key, dod_key = _zt_target_key(p1, CISA), _zt_target_key(p2, DOD)
        merged["targets"] = {
            **{k: v for k, v in p2["targets"].items() if v["kind"] != "zt"},
            f"zt:{CISA}": p1["targets"][cisa_key],
            f"zt:{DOD}": p2["targets"][dod_key],
        }
        if CAPPED_TARGET_KEY in p2 or CAPPED_TARGET_KEY in p1:
            merged[CAPPED_TARGET_KEY] = {
                f"zt:{CISA}": list(p1.get(CAPPED_TARGET_KEY, {}).get(cisa_key, [])),
                f"zt:{DOD}": list(p2.get(CAPPED_TARGET_KEY, {}).get(dod_key, [])),
            }
        # Copy-then-reassign: an in-place edit of a JSON column is not saved.
        dod_reg.provenance = merged
        s.commit()
