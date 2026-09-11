"""Risk Register schemas (Work Order E)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RiskGateStatus(BaseModel):
    """Whether the Risk Register can be generated for a client.

    Threshold: a MITRE ATT&CK coverage mapping AND at least one of (CSF, ZT).
    """

    unlocked: bool
    has_attack: bool
    has_csf: bool
    has_zt: bool
    # ABSENT — no assessment of this kind exists. Remedy: create one.
    missing: list[str]
    # EXISTS but is not APPROVED or RELEASED, so it cannot be synthesized into a
    # register that will be exported under the client's name (#237). Remedy:
    # approve it.
    #
    # **REPORTING, NOT BLOCKING.** An entry here does not necessarily stop
    # generation — `synthesizable_missing` decides that, and it mirrors the
    # unlock rule. A draft ZT beside an approved CSF appears here, does not
    # block, and is disclosed on the register as an excluded input.
    #
    # A SEPARATE FIELD, deliberately, though both feed one sentence. "There is no
    # ATT&CK mapping" and "the ATT&CK mapping is a draft" are different facts
    # with different remedies, and putting the second into a field named
    # `missing` would make the API assert something untrue in order to serve a
    # message. #234 shipped exactly that (`not_recorded` borrowed to mean
    # "retired") and had to correct it; it is not repeated here one issue later.
    #
    # Defaulted, so an older client parses a newer response (the C0 pattern).
    not_finalized: list[str] = []
    # What actually BLOCKS generation, and it mirrors `missing`'s rule over
    # FINALIZED inputs: an approved ATT&CK mapping, and an approved CSF or ZT.
    #
    # Distinct from `not_finalized`, which REPORTS. An earlier version refused on
    # any entry in that list, which exceeded the unlock rule -- CSF and ZT are
    # alternatives, so a draft ZT beside an approved CSF blocked a register the
    # gate said was available. Two fields because they answer two questions:
    # "what is unapproved" and "what stops you". Merging them is what produced
    # the defect.
    synthesizable_missing: list[str] = []


class RiskEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    axis: str | None
    source: str | None
    source_id: str | None
    linked_techniques: list[str] | None
    linked_controls: list[str] | None
    likelihood: str | None
    impact: str | None
    tier: str | None
    compensating_controls: str | None
    residual_risk: str | None
    recommended_action: str | None
    rationale: str | None
    origin: str
    trust: str | None
    # #132. What the model proposed for this entry's link fields and lost.
    # `None` means pre-0048 and NOT "nothing"; `{}` is the positive claim that
    # nothing was dropped. A renderer that treats the two alike reinstates the
    # defect the column was added for.
    dropped_links: dict | None = None


class RiskRegisterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    version: int
    generated_by: uuid.UUID | None
    finalized_at: datetime | None
    created_at: datetime
    # Assessments that EXIST for this client and contributed nothing, because
    # they are not approved (#237). Empty for a fully-approved client.
    #
    # Required rather than optional-in-spirit: once the provenance refusal was
    # narrowed to mirror the unlock rule, an unapproved OPTIONAL input stopped
    # blocking and started being silently omitted. A register built over a
    # withheld population is not self-describing -- `CLAUDE.md`'s coverage-
    # percentage rule -- so the withheld set is rendered beside it. Without this
    # the fix would have traded a hard block for a quiet partial, which is the
    # worse of the two.
    #
    # WHERE IT IS RENDERED, and where it is not. The sentence above was written
    # in the present tense before any surface read the field, and for one review
    # round nothing did: five occurrences in the tree, none of them a consumer.
    #
    # [2026-09-11, #244] The note that stood here said "It is NOT persisted, so
    # `GET .../register/latest` returns `[]` ... Those three surfaces need a
    # migration and are #240." The migration LANDED -- 0047 stores the set in
    # `risk_registers.provenance["excluded"]` -- and the note kept saying one
    # was needed, which is a stale deferral sitting exactly where a reader goes
    # to check. Nothing had to be built; `_serialize` simply never read it back.
    #
    # Now: the admin Risk Register page renders it as a banner, and `latest`
    # returns the persisted set, so the banner survives a reload.
    #
    # STILL TRUE, and still the reason not to read "is rendered beside it" as
    # covering everything: it does NOT reach the exported XLSX/PDF/Word, and it
    # does NOT reach the client dashboard. Those two remain, and the population
    # they are about is the one a client actually receives.
    excluded_inputs: list[str] = []
    #: Whether `excluded_inputs` is an ANSWER or a SILENCE.
    #:
    #: `False` means this register predates provenance recording (NULL
    #: `provenance`, pre-0047), so nothing on file says what was left out --
    #: which is not the same fact as "nothing was left out", and an empty list
    #: cannot tell them apart.
    #:
    #: DEFAULTED FALSE, and the direction is the point. `_serialize` sets it
    #: explicitly on every path, so the default is reached only by a payload
    #: that predates this field -- which is exactly a register whose exclusions
    #: were never recorded, so `False` is the TRUE answer there as well as the
    #: safe one. `CLAUDE.md`: missing data defaults to UNCONFIRMED, never to
    #: confirmed. A `True` default would have let any future writer that
    #: forgets the field certify a clean input set it never looked at.
    excluded_inputs_recorded: bool = False
    xlsx_artifact_id: uuid.UUID | None = None
    pdf_artifact_id: uuid.UUID | None = None
    docx_artifact_id: uuid.UUID | None = None
    xlsx_filename: str | None = None
    pdf_filename: str | None = None
    docx_filename: str | None = None
    entries: list[RiskEntryResponse]
    # Dashboard rollups (code-computed).
    tier_counts: dict[str, int] = {}
    axis_counts: dict[str, int] = {}
    action_counts: dict[str, int] = {}
    # risk_synthesize runs as concurrent batches (one llm_calls row each).
    # Additive + defaulted so older clients and stored payloads parse unchanged
    # (C0). A partial run KEEPS what succeeded rather than discarding it, so the
    # consultant must be told the draft is incomplete and by how much. Both are
    # 0 on a register read back from storage — they describe a generate run, not
    # the register itself.
    batches_total: int = 0
    batches_failed: int = 0

    # #121's outcome counter, reaching the CALLER and not only the audit blob.
    #
    # An entry stored with no tier renders as em dashes in the register, is
    # dropped from the 5x5 matrix, and is counted by `total_entries` -- so a
    # register can report forty open risks whose matrix sums to fewer than
    # forty, with nothing saying why. That is the #121 client outcome, and it
    # has two causes: a value the model supplied that would not resolve, and a
    # key it simply omitted. This counts the OUTCOME, so it is non-zero under
    # either.
    #
    # DERIVED from the stored entries rather than passed in from the generate
    # run, deliberately. `batches_*` describe a run and are 0 on a read-back;
    # these describe the REGISTER, so they are correct whenever it is read.
    # A derived value cannot be out of sync; a passed one merely is not, yet.
    entries_total: int = 0
    entries_without_tier: int = 0

    # #132, the same instrument pointed at the LINKS.
    #
    # `linked_techniques = []` was byte-identical whether the model proposed
    # nothing or proposed five things that all failed to resolve, so a
    # consultant read "the AI found no ATT&CK relevance" over "the AI proposed
    # five techniques and all five were misspelled".
    #
    # THREE counters rather than one, because there are three states and a
    # two-state reading is what the column exists to end:
    #
    #   entries_with_dropped_links     the model offered something that did not
    #                                  resolve -- what to look at.
    #   entries_unlinked_after_drops   ... and NOTHING survived, so the entry
    #                                  renders exactly like one nobody linked.
    #                                  The client-visible outcome.
    #   entries_links_not_recorded     pre-0048 rows. "Nothing was dropped" and
    #                                  "nobody was counting" are different
    #                                  facts and this keeps them apart.
    #
    # DERIVED from the stored entries, like `entries_without_tier` and for the
    # same reason: they describe the REGISTER, so they are correct whenever it
    # is read, not only on the response to the generate run. That is only
    # possible because the drop is PERSISTED (migration 0048); a counter alone
    # would be 0 on every read-back and the harm outlives the run.
    entries_with_dropped_links: int = 0
    entries_unlinked_after_drops: int = 0
    entries_links_not_recorded: int = 0
