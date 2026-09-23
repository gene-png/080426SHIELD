"""Deliverable - the finalized PDF / XLSX pair for a service.

  deliverables    id, service_id, title, summary, version,
                  pdf_artifact_id, xlsx_artifact_id, finalized_at,
                  finalized_by, superseded_by

Deliverables are generated and versioned by admins. Sprint 5 (D-025)
reintroduced an explicit release-to-client step (Master Spec §12): until a
consultant sets `released_at`, the client sees nothing — no draft, no AI
output, no download. This is a NEW single-role release action, not a revival
of the removed D-005/D-006 reviewer gate (D-023). `version`/`superseded_by`
keep internal history.

Filenames follow Master Spec §15.5: `{Company}_{Service}{MMDDYY}.{ext}`.
The slugifier lives in app.deliverables.filename (Phase 3 stage 8).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._common import TimestampMixin, UUIDPKMixin

#: `Deliverable.frozen_target_source` values (#209, migration 0051). NOT the
#: resolver's source vocabulary -- see the column comment, where the distinction
#: is the whole point. These say HOW THE FREEZE WAS ESTABLISHED.
#:
#: The constant sits HERE, beside the column, rather than in the routes that
#: write it: the window is closed by whoever edits the column's meaning, and
#: they would otherwise have no way to know two routes carry the literal.
FROZEN_TARGET_AT_FINALIZE = "finalize"
#: Written only by migration 0051's two backfills. No product code sets either,
#: and a test asserting that is what stops a later route reaching for one.
FROZEN_TARGET_FROM_AUDIT = "audit"
FROZEN_TARGET_FROM_UPDATED_AT = "updated_at"


class Deliverable(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "deliverables"

    service_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    pdf_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL")
    )
    xlsx_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL")
    )
    # Word (.docx) deliverable (Work Order C4), alongside PDF + XLSX.
    docx_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL")
    )

    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finalized_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    # The PARENT version this deliverable was built from — the assessment or
    # capability-list version, not `version` above, which is the deliverable's
    # own independent counter (W4, migration 0041).
    #
    # Stamped at finalize, which is where the content freezes against a specific
    # parent and where the parent is already required to be APPROVED. Release
    # reads it to flip exactly that row to RELEASED. Without it the only
    # available rule is "latest APPROVED", which flips the wrong row after
    # approve v1 -> finalize -> cut v2 -> approve v2 -> release.
    #
    # Not a ForeignKey: the four parents live in four different tables, so there
    # is no single referent. `(service_id, parent_version)` is unique because
    # every parent table constrains `(service_id, version)`.
    #
    # NULL = finalized before 0041. Release leaves those parents alone and logs
    # it rather than guessing (C0: older rows parse unchanged).
    parent_version: Mapped[int | None] = mapped_column(Integer)

    # THE ENGAGEMENT TARGET THIS DELIVERABLE WAS RENDERED AGAINST (#209,
    # migration 0051). Structurally twinned with `parent_version` above: same
    # table, same nullable shape, same "NULL = predates this migration"
    # contract, stamped at the same moment and for the same reason.
    #
    # Before this, a client dashboard resolved the target LIVE on every request
    # while the released document held a number frozen at finalize. Change the
    # intake target after release and the two disagree -- the PDF says "37 gaps
    # at target S4" and the dashboard beside it says something else, computed
    # from the same approved answers. Both are internally consistent and one is
    # a number the client never contracted for.
    #
    # STAMPED AT FINALIZE, NOT RELEASE, and that distinction is the whole
    # correctness argument. The artifacts are rendered at finalize -- the
    # renderers run there, and `deliverable_release.py` rebuilds nothing -- so a
    # release-time stamp would record a target the artifacts never used, putting
    # the provenance and the document it describes in disagreement. That is #209
    # reintroduced by #209's own fix. Each re-finalize mints a new row, so
    # per-row stamping at finalize is exactly what 0041 already does.
    #
    # `frozen_target` HOLDS THE CLIENT'S CHOSEN VALUE, NOT THE RESOLVED ONE.
    # It is `csf_target_tier` or `zt_target_stage` off the source request -- a
    # `SmallInteger | None` -- and the read paths run the SAME resolver they run
    # today (`zt_resolve_target_stage` / `csf_resolve_target_tier`) over it.
    # Freezing the resolver's OUTPUT would make the number and its caption two
    # stored values kept in agreement with a pure function by hand; freezing its
    # INPUT makes them a derivation that cannot disagree.
    #
    # `frozen_target_source` IS THE DISCRIMINATOR, AND ITS NAME IS A TRAP. The
    # field it sits beside in every response -- `target_stage_source` /
    # `target_tier_source` -- is the RESOLVER's verdict (`client`, `default`,
    # `client_out_of_range`, `client_unparseable`). This column is nothing of the
    # kind. It records HOW THE FREEZE WAS ESTABLISHED: `finalize` (stamped by the
    # finalize route), `audit` or `updated_at` (backfilled by 0051), or NULL --
    # never frozen.
    #
    # It exists because `frozen_target IS NULL` otherwise carries two facts. A
    # client who chose no target has a legitimately NULL choice, frozen exactly;
    # a deliverable predating 0051 has no freeze at all. Same bytes, opposite
    # meanings, and only the second may fall back to live computation. EVERY READ
    # PATH THEREFORE BRANCHES ON `frozen_target_source IS NULL`, NEVER ON
    # `frozen_target IS NULL`.
    #
    # ONE PAIR, NOT TWO PER LADDER: `Service.kind` discriminates, so a CSF
    # deliverable's `frozen_target` is a tier and a ZT one's is a stage. Two
    # pairs would need every reader to know which was populated, and the kind
    # already answers that.
    #
    # AND A THIRD READING OF NULL, which the `Service.kind` argument above
    # implies without stating: an ATT&CK or Tech Debt deliverable has NO
    # engagement target of this shape at all, so the pair stays NULL on those
    # rows forever and nothing reads it. Only the CSF and ZT finalize routes
    # stamp, which is why this is two routes and not the four that stamp
    # `parent_version`. A reader who generalises from `parent_version` to "all
    # four finalize routes" would file the absence as a bug.
    #
    # An unfrozen row means COMPUTE LIVE AND SAY SO -- never a silent fallback,
    # which would be today's behaviour re-shipped under a new field name. The
    # disclosure is `target_frozen_at` on the dashboard responses, and null IS
    # the disclosure.
    frozen_target: Mapped[int | None] = mapped_column(Integer)
    frozen_target_source: Mapped[str | None] = mapped_column(String(16))

    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("deliverables.id", ondelete="SET NULL")
    )

    # Release-to-client (D-025, Master Spec §12): null = unreleased (client sees
    # nothing). Set once by an admin via the release route; SET NULL on the
    # releasing user's deletion so the deliverable outlives them.
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
