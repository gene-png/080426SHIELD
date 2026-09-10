"""Pre-populate an engagement's hand-entered assessment data.

## Why this exists

`09-the-data-entry-problem.md` established the arithmetic: a complete
engagement needs roughly 800 individual field entries, and AI fills almost
none of them. The sharp case is NIST CSF -- `Run AI (csf_score)` writes
`CsfDimensionScore` (the admin Playbook panel) and NEVER writes
`CsfAnswer.maturity_tier`, which is the only input to the client dashboard
and the released deliverable. The only two write paths for a tier are
`PATCH /answers/{answer_id}` and `PATCH /self-assessment/answers/{answer_id}`,
one row each. There is no bulk endpoint, so 106 subcategories means 106
requests.

A demonstration recording cannot contain that, and should not pretend to. The
decision recorded in that document is to pre-populate off-camera and record
the consultant's JUDGEMENT rather than their typing. This script is that
pre-population step.

## What it writes, and what it deliberately does not

  * **NIST CSF** -- `maturity_tier` on every subcategory answer.
  * **Zero Trust (CISA and DoD)** -- `maturity_stage` and `target_stage` on
    every capability answer.
  * **Technical Debt** -- `category`, `annual_cost_usd`, `license_count` and
    `disposition` on capability rows that are missing them.

  * **MITRE ATT&CK is deliberately untouched.** Its 633 rows are filled by
    `Run AI` on camera, which genuinely works and is the platform's most
    impressive single act. The service with the most rows is the one the
    platform fills for you, and that contrast is worth demonstrating rather
    than erasing.

## Why it writes to the database rather than through the API

Same reason `seed_demo.py` does: this is off-camera setup, not a
demonstration of the product's own write paths. 193 CSF/ZT rows through
per-row HTTP PATCHes costs minutes and an auth session to accomplish what one
transaction does. The values written are the same values those endpoints
would write, and the range validation each endpoint performs at its boundary
is reproduced here against the same catalogs (see `_check_range`).

## The posture it encodes

The profile in `02-fictional-organization.md`, not a uniform fill. A flat
profile reads as a demo; a differentiated one is what makes the gap analysis
and the Risk Register synthesis say anything. CSF is Protect-strong /
Recover-weak (the honest signature of a compliance-driven programme); Zero
Trust has Identity strongest and Automation & Orchestration visibly at the
floor.

## Usage

    docker compose exec -T api sh -lc \\
      "cd /app && python -m scripts.prepopulate_engagement --client-name 'X'"

    # See what would change without writing:
    ... --client-name 'X' --dry-run

This script NEVER creates a client, a service or an assessment. It fills in
what already exists and fails loudly when something it expects is absent,
because "the client has no CSF assessment" and "the CSF assessment is already
fully scored" must not be the same silent success.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))


def _ensure_db_url() -> None:
    if "DATABASE_URL" not in os.environ:
        raise SystemExit(
            "prepopulate: DATABASE_URL is not set. Run this inside the api "
            "container (docker compose exec -T api sh -lc 'cd /app && ...'), "
            "where compose provides it. Refusing to guess a database."
        )


_ensure_db_url()

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.csf.catalog import FUNCTIONS, subcategories_for_function  # noqa: E402
from app.models.capability import (  # noqa: E402
    CapabilityDisposition,
    CapabilityItem,
    CapabilityList,
)
from app.models.client import Client  # noqa: E402
from app.models.csf_assessment import CsfAnswer, CsfAssessment  # noqa: E402
from app.models.zt_assessment import (  # noqa: E402
    ZtAnswer,
    ZtAssessment,
    ZtFramework,
)
from app.zt.catalog import capabilities as zt_capabilities  # noqa: E402

LOG = "prepopulate:"

# ---------------------------------------------------------------------------
# The posture profile
#
# Each entry is a CYCLE, not a single value. Cycling a short tuple across a
# function's subcategories produces a differentiated profile deterministically
# -- same input, same output, every run -- while avoiding the flat fill that
# makes a demonstration look staged. The cycle's shape carries the story: a
# function whose tuple is mostly 3s with a 4 is "strongest"; one that is 1s
# with a single 2 is "weakest".
#
# Tiers are 1..4 (CsfAnswer.maturity_tier). Source: 02-fictional-organization.md
# section 5, "NIST CSF 2.0".
# ---------------------------------------------------------------------------
CSF_TIER_CYCLES: dict[str, tuple[int, ...]] = {
    # SOC 2 gave them policy, not oversight.
    "GV": (2, 2, 3, 2),
    # Good asset inventory in GovCloud, poor in the legacy account -- so this
    # one is genuinely bimodal rather than middling-everywhere.
    "ID": (3, 2, 2, 3, 1),
    # Strongest. This is what HIPAA and SOC 2 actually test.
    "PR": (3, 4, 3, 3, 4),
    # The SIEM is real but only partially fed.
    "DE": (2, 3, 2, 2),
    # A plan exists; it has never been exercised.
    "RS": (2, 1, 2, 1),
    # Weakest. Backups have never been restored end to end.
    "RC": (1, 2, 1, 1),
}

# Zero Trust target stages, set PER PILLAR rather than per capability.
#
# The obvious rule -- target = current + 1 everywhere -- is wrong here, and the
# reason is measured rather than aesthetic. `_gather_findings` in
# `app/routes/risk.py` raises a Risk Register finding for every ZT answer where
# `maturity_stage < target_stage`, and the fixture emits exactly ONE REGISTER
# ENTRY PER FINDING with no cap, dedup or severity filter. So "one above
# current, everywhere" makes every capability below the ceiling a finding, and
# the register becomes a wall of entries nobody can read -- the opposite of the
# "small number of high-severity entries" the profile asks for.
#
# A pillar-level planned target is also what a real 12-month plan looks like:
# the client picks a stage per pillar, and the capabilities already at or above
# it are not gaps. Capabilities below it are, and those are the ones worth
# talking about on camera.
ZT_CISA_PILLAR_TARGETS: dict[str, int] = {
    "ID": 4,  # Already strong; push the last capability to Optimal.
    "DV": 3,
    "NW": 2,  # Weak, and a realistic plan does not leap to Optimal.
    "AW": 3,
    "DT": 3,
    "VA": 3,
    "AO": 2,  # From the floor, one rung is the honest 12-month ambition.
    "GV": 3,
}

ZT_DOD_PILLAR_TARGETS: dict[str, int] = {
    "USR": 3,
    "DEV": 2,
    "APP": 2,
    "DAT": 3,
    "NET": 2,
    "VIS": 2,
    "AUT": 2,
}

# Zero Trust, CISA ZTMM 2.0 -- stages 1..4.
# Source: 02-fictional-organization.md section 5, "Zero Trust (CISA ZTMM 2.0)".
ZT_CISA_STAGE_CYCLES: dict[str, tuple[int, ...]] = {
    "ID": (3, 3, 4, 3),  # Okta, MFA, joiner-mover-leaver works. HIPAA drove it.
    "DV": (2, 3, 2),  # Managed and monitored, but EDR stops at the laptop.
    "NW": (1, 2, 1),  # Flat VPC; security groups as the only boundary.
    "AW": (3, 1, 1, 2),  # Strong build-time scanning, no runtime protection.
    "DT": (3, 2, 3, 2),  # Encryption everywhere, classification nowhere.
    "VA": (2, 2, 3, 1),  # Good cloud telemetry, no endpoint/workload telemetry.
    "AO": (1, 1, 1, 1),  # Nothing automated. Visibly the floor, on purpose.
    "GV": (2, 2, 1, 2),  # Policy exists; enforcement is manual.
}

# Zero Trust, DoD ZTRA -- stages 1..3. A three-rung ladder, so the same story
# is told with less room: the floor and the ceiling are one step apart.
ZT_DOD_STAGE_CYCLES: dict[str, tuple[int, ...]] = {
    "USR": (3, 2, 3, 2),  # Identity is their strength here too.
    "DEV": (2, 2, 1),
    "APP": (1, 2, 1),  # No runtime protection on the workloads.
    "DAT": (2, 2, 3),
    "NET": (1, 2, 1),
    "VIS": (2, 1, 2),
    "AUT": (1, 1, 1),  # The floor, matching CISA's AO.
}

# Technical Debt category and cost defaults, keyed by a lowercase substring of
# the row's name. Deliberate overlaps: two cloud scanners share a category and
# two rows share a vendor, because the Overlap dashboard reads "No categories
# with more than one item." / "No vendor repeats." on an estate that has none,
# and a real estate has both.
TECH_DEBT_DEFAULTS: tuple[tuple[str, str, float, int], ...] = (
    ("crowdstrike", "Endpoint Detection & Response", 148_000.00, 1_200),
    ("falcon", "Endpoint Detection & Response", 148_000.00, 1_200),
    ("splunk", "SIEM & Log Management", 265_000.00, 400),
    ("okta", "Identity & Access Management", 96_000.00, 1_150),
    ("tenable", "Cloud Security Posture", 74_000.00, 500),
    ("wiz", "Cloud Security Posture", 88_000.00, 500),
    ("qualys", "Cloud Security Posture", 61_000.00, 350),
    ("vault", "Secrets Management", 42_000.00, 250),
    ("snyk", "Application Security Testing", 55_000.00, 300),
    ("veeam", "Backup & Recovery", 38_000.00, 120),
    ("proofpoint", "Email Security", 71_000.00, 1_150),
    ("cloudflare", "Network & Edge Security", 45_000.00, 1),
)
TECH_DEBT_FALLBACK = ("Uncategorized Tooling", 25_000.00, 100)


class PrepopulateError(RuntimeError):
    """Raised when the world is not in a state this script can fill in.

    Deliberately distinct from "there was nothing to do": every raise site
    below names what it looked for and what it found instead, because a
    pre-population step that silently writes nothing is indistinguishable
    from one that worked until the take is already running.
    """


def _check_range(value: int, low: int, high: int, what: str) -> int:
    """Reproduce the range validation the API route performs at its boundary.

    Writing to the database bypasses the endpoint, so it must not bypass the
    endpoint's validation -- a stage of 5 in a four-stage framework renders as
    the fault string "Unknown" on camera, and nothing else would catch it.
    """
    if not isinstance(value, int) or isinstance(value, bool):
        raise PrepopulateError(f"{what}: {value!r} is not an int")
    if not low <= value <= high:
        raise PrepopulateError(f"{what}: {value} is outside {low}..{high}")
    return value


def _resolve_client(db: Session, name: str | None, cid: str | None) -> Client:
    if cid:
        try:
            parsed = uuid.UUID(cid)
        except ValueError as exc:
            raise PrepopulateError(f"--client-id {cid!r} is not a UUID") from exc
        found = db.get(Client, parsed)
        if found is None:
            raise PrepopulateError(f"no client with id {cid}")
        return found

    if not name:
        raise PrepopulateError("give --client-name or --client-id")

    rows = db.scalars(select(Client).where(Client.legal_name == name)).all()
    if not rows:
        known = db.scalars(select(Client.legal_name)).all()
        raise PrepopulateError(f"no client with legal_name {name!r}. Known: {sorted(known)}")
    if len(rows) > 1:
        raise PrepopulateError(f"{len(rows)} clients share legal_name {name!r}; use --client-id")
    return rows[0]


def _editable(status: object) -> bool:
    """Only draft and submitted assessments accept edits.

    `approved` and `released` are locked by the API (409 "This assessment is
    locked."), and writing under them from a script would produce a state the
    product itself refuses to create.
    """
    return str(status) in {"draft", "submitted"}


def _latest_assessment(rows: list, label: str):
    """Pick the highest-version non-discarded assessment, or explain why not.

    The three outcomes are kept distinct on purpose. "No assessment exists",
    "every assessment is discarded" and "the current one is locked" need
    different actions from whoever ran this, and collapsing them into one
    message sends them looking in the wrong place.
    """
    if not rows:
        raise PrepopulateError(f"{label}: no assessment exists. Create it first.")
    live = [r for r in rows if str(r.status) != "discarded"]
    if not live:
        raise PrepopulateError(f"{label}: all {len(rows)} assessment(s) are discarded.")
    latest = max(live, key=lambda r: r.version)
    if not _editable(latest.status):
        raise PrepopulateError(
            f"{label}: v{latest.version} is {latest.status} and therefore locked. "
            "Pre-populate before approving, or start a new version."
        )
    return latest


def prepopulate_csf(db: Session, client: Client, dry_run: bool) -> dict[str, int]:
    """Write a maturity tier to every CSF subcategory answer."""
    rows = list(db.scalars(select(CsfAssessment).where(CsfAssessment.client_id == client.id)).all())
    assessment = _latest_assessment(rows, "CSF")

    answers = list(
        db.scalars(select(CsfAnswer).where(CsfAnswer.assessment_id == assessment.id)).all()
    )
    if not answers:
        raise PrepopulateError(
            f"CSF v{assessment.version} has no answer rows. An assessment "
            "normally seeds one answer per subcategory at creation; this one "
            "did not, so there is nothing to fill in."
        )

    by_code = {a.subcategory_code: a for a in answers}
    written = 0
    skipped_locked = 0
    below_tier_3 = 0

    for fn in FUNCTIONS:
        cycle = CSF_TIER_CYCLES.get(fn.code)
        if cycle is None:
            raise PrepopulateError(
                f"CSF function {fn.code!r} has no tier cycle in this script's "
                "profile. The catalog has a function the profile does not "
                "cover -- add it rather than letting it stay unscored."
            )
        for i, sub in enumerate(subcategories_for_function(fn.code)):
            answer = by_code.get(sub.code)
            if answer is None:
                raise PrepopulateError(
                    f"CSF v{assessment.version}: no answer row for {sub.code}. "
                    "The assessment is missing a subcategory the catalog has."
                )
            if answer.locked:
                skipped_locked += 1
                continue
            tier = _check_range(cycle[i % len(cycle)], 1, 4, f"CSF {sub.code}")
            if tier < 3:
                below_tier_3 += 1
            if answer.maturity_tier != tier:
                if not dry_run:
                    answer.maturity_tier = tier
                written += 1

    # Same accounting as ZT: `_gather_findings` raises one finding per answer
    # scored below tier 3, and fixture mode turns each into a register entry.
    print(
        f"{LOG} CSF v{assessment.version} ({assessment.status}): "
        f"{written} tier(s) set, {skipped_locked} locked row(s) left alone, "
        f"{len(answers)} answer row(s) total; "
        f"{below_tier_3} below tier 3 -> {below_tier_3} risk finding(s)"
    )
    return {
        "written": written,
        "locked": skipped_locked,
        "total": len(answers),
        "findings": below_tier_3,
    }


def prepopulate_zt(
    db: Session, client: Client, framework: ZtFramework, dry_run: bool
) -> dict[str, int]:
    """Write current and target stages to every ZT capability answer."""
    label = f"ZT {framework.value}"
    rows = list(
        db.scalars(
            select(ZtAssessment).where(
                ZtAssessment.client_id == client.id,
                ZtAssessment.framework == framework,
            )
        ).all()
    )
    assessment = _latest_assessment(rows, label)

    answers = list(
        db.scalars(select(ZtAnswer).where(ZtAnswer.assessment_id == assessment.id)).all()
    )
    if not answers:
        raise PrepopulateError(f"{label} v{assessment.version} has no answer rows.")

    is_cisa = framework == ZtFramework.CISA_ZTMM_2_0
    cycles = ZT_CISA_STAGE_CYCLES if is_cisa else ZT_DOD_STAGE_CYCLES
    targets = ZT_CISA_PILLAR_TARGETS if is_cisa else ZT_DOD_PILLAR_TARGETS
    max_stage = 4 if is_cisa else 3

    by_code = {a.capability_code: a for a in answers}
    seen: dict[str, int] = {}
    gaps: dict[str, int] = {}
    written = 0

    for cap in zt_capabilities(framework.value):
        cycle = cycles.get(cap.pillar_code)
        if cycle is None:
            raise PrepopulateError(
                f"{label}: pillar {cap.pillar_code!r} has no stage cycle in "
                "this script's profile."
            )
        answer = by_code.get(cap.code)
        if answer is None:
            raise PrepopulateError(f"{label} v{assessment.version}: no answer row for {cap.code}.")
        i = seen.get(cap.pillar_code, 0)
        seen[cap.pillar_code] = i + 1

        current = _check_range(cycle[i % len(cycle)], 1, max_stage, f"{label} {cap.code}")
        planned = targets.get(cap.pillar_code)
        if planned is None:
            raise PrepopulateError(f"{label}: pillar {cap.pillar_code!r} has no planned target.")
        # The pillar's planned stage, never below what they already have --
        # a target under current would render as a negative gap.
        target = _check_range(max(planned, current), 1, max_stage, f"{label} {cap.code} target")
        gaps[cap.pillar_code] = gaps.get(cap.pillar_code, 0) + (1 if current < target else 0)

        if answer.maturity_stage != current or answer.target_stage != target:
            if not dry_run:
                answer.maturity_stage = current
                answer.target_stage = target
            written += 1

    # The gap count is not decoration: every capability with current < target
    # becomes one Risk Register finding, and in fixture mode one register
    # entry. Printing it here is the only place anyone sees that number before
    # they press Generate.
    total_gaps = sum(gaps.values())
    by_pillar = " ".join(f"{p}={n}" for p, n in sorted(gaps.items()))
    print(
        f"{LOG} {label} v{assessment.version} ({assessment.status}): "
        f"{written} answer(s) set, {len(answers)} row(s) total; "
        f"{total_gaps} gap(s) -> {total_gaps} risk finding(s) [{by_pillar}]"
    )
    return {"written": written, "total": len(answers), "gaps": total_gaps}


def prepopulate_tech_debt(db: Session, client: Client, dry_run: bool) -> dict[str, int]:
    """Fill category, cost, licence count and disposition on capability rows.

    These are the fields whose absence the client dashboard renders as `-`
    and whose absence downgrades the spend KPI to a "Floor - some tools
    lacked a cost" caption.
    """
    lists = list(
        db.scalars(select(CapabilityList).where(CapabilityList.client_id == client.id)).all()
    )
    if not lists:
        raise PrepopulateError(
            "Tech Debt: this client has no capability list. Upload an "
            "inventory and run Extract first -- this script fills rows in, it "
            "does not invent an estate."
        )
    live = [lst for lst in lists if str(lst.status) != "discarded"]
    if not live:
        raise PrepopulateError("Tech Debt: every capability list is discarded.")
    lst = max(live, key=lambda x: getattr(x, "version", 0) or 0)
    if str(lst.status) not in {"draft"}:
        raise PrepopulateError(
            f"Tech Debt: list is {lst.status}; only a draft accepts edits "
            '(the API returns 409 "This capability list has been released '
            'and is locked.").'
        )

    items = list(
        db.scalars(select(CapabilityItem).where(CapabilityItem.capability_list_id == lst.id)).all()
    )
    if not items:
        raise PrepopulateError(
            f"Tech Debt: capability list {lst.id} has no rows. Run Extract on "
            "a real inventory -- an empty or unparseable file falls back to "
            "three canned demo items with no security classification."
        )

    filled_category = filled_cost = filled_licences = filled_disposition = 0

    for idx, item in enumerate(items):
        if item.locked:
            continue
        name = (item.name or "").lower()
        category, cost, licences = TECH_DEBT_FALLBACK
        for needle, cat, c, lic in TECH_DEBT_DEFAULTS:
            if needle in name:
                category, cost, licences = cat, c, lic
                break

        if item.category is None:
            if not dry_run:
                item.category = category
            filled_category += 1
        if item.annual_cost_usd is None:
            if not dry_run:
                item.annual_cost_usd = cost
            filled_cost += 1
        if item.license_count is None:
            if not dry_run:
                item.license_count = licences
            filled_licences += 1
        if item.disposition is None:
            # Mostly keep, with a periodic consolidate and cut so the
            # Consolidation plan has something to say. An estate where every
            # row is "keep" produces an empty plan.
            choice = (
                CapabilityDisposition.CONSOLIDATE
                if idx % 5 == 4
                else CapabilityDisposition.CUT if idx % 7 == 6 else CapabilityDisposition.KEEP
            )
            if not dry_run:
                item.disposition = choice
            filled_disposition += 1

    print(
        f"{LOG} Tech Debt list {lst.id} ({lst.status}): {len(items)} row(s); "
        f"filled category={filled_category} cost={filled_cost} "
        f"licences={filled_licences} disposition={filled_disposition}"
    )
    return {
        "rows": len(items),
        "category": filled_category,
        "cost": filled_cost,
        "licences": filled_licences,
        "disposition": filled_disposition,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pre-populate hand-entered assessment data for a demo run."
    )
    parser.add_argument("--client-name", help="exact Client.legal_name")
    parser.add_argument("--client-id", help="Client.id (UUID)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would change and write nothing",
    )
    parser.add_argument(
        "--skip",
        default="",
        help="comma-separated: csf,zt-cisa,zt-dod,tech-debt. A service the "
        "client does not have must be skipped EXPLICITLY -- its absence is "
        "an error, never a silent zero.",
    )
    args = parser.parse_args(argv)

    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    known = {"csf", "zt-cisa", "zt-dod", "tech-debt"}
    if not skip <= known:
        print(f"{LOG} unknown --skip value(s): {sorted(skip - known)}", file=sys.stderr)
        return 2

    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    with Session(engine) as db:
        try:
            client = _resolve_client(db, args.client_name, args.client_id)
        except PrepopulateError as exc:
            print(f"{LOG} {exc}", file=sys.stderr)
            return 2

        print(
            f"{LOG} client {client.legal_name!r} ({client.id})"
            f"{' [DRY RUN -- nothing will be written]' if args.dry_run else ''}"
        )

        failures: list[str] = []
        for key, fn in (
            ("csf", lambda: prepopulate_csf(db, client, args.dry_run)),
            (
                "zt-cisa",
                lambda: prepopulate_zt(db, client, ZtFramework.CISA_ZTMM_2_0, args.dry_run),
            ),
            (
                "zt-dod",
                lambda: prepopulate_zt(db, client, ZtFramework.DOD_ZTRA, args.dry_run),
            ),
            ("tech-debt", lambda: prepopulate_tech_debt(db, client, args.dry_run)),
        ):
            if key in skip:
                print(f"{LOG} {key}: skipped by --skip")
                continue
            try:
                fn()
            except PrepopulateError as exc:
                # Collect rather than abort: one missing service must not hide
                # what the other three would have reported.
                failures.append(f"{key}: {exc}")
                print(f"{LOG} {key}: FAILED -- {exc}", file=sys.stderr)

        if failures:
            db.rollback()
            print(
                f"{LOG} {len(failures)} service(s) failed; NOTHING was "
                "written. Fix them, or pass --skip for the ones this client "
                "genuinely does not have.",
                file=sys.stderr,
            )
            return 1

        if args.dry_run:
            db.rollback()
            print(f"{LOG} dry run complete; rolled back.")
            return 0

        # The commit is what makes the writes true, so the success record goes
        # BELOW it, never above.
        db.commit()
        print(f"{LOG} committed.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
