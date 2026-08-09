# ATT&CK AI inputs, citation resolver, and workspace redesign

**Status as of 2026-08-08.** This was a machine-local planning file; it is copied
into the repo so it is reviewable rather than living on one laptop. It is a
record of decisions, not a spec — where it disagrees with the code, the code
wins and this file needs a correction.

## What a reader needs to know before reading it

| Part    | Subject                                                    | State                                                    |
| ------- | ---------------------------------------------------------- | -------------------------------------------------------- |
| 1       | `/ai-inputs` visibility + enriched capability payload      | **Written, on PR #29, NOT merged**                       |
| 2       | Workspace redesign, freeze-on-generate, DRAFT watermarking | **Not started**                                          |
| 3       | Reopen endpoint x4 + shared release-staleness guard        | **Not started.** Tests committed as `xfail(strict=True)` |
| 4       | Handoff notes                                              | Historical                                               |
| 5 / 5.1 | Citation resolver rewrite + the scoring rule               | **Not started — this is the next task**                  |

**PR #29 is green in CI and must not merge.** An adversarial audit
(`.claude/agents/adversarial-reviewer.md`) found 13 defects the suite does not
catch, two of them mine and introduced by fixes that each looked complete. The
full finding set, both audit passes, and the decisions taken on each are on
**GitHub issue #30**, which is the live record — this file is the plan, the issue
is the evidence.

The merge is gated on a clean adversarial audit, not on CI. Green tests are
exactly what let both defects through.

## Why the resolver needs a rewrite rather than a third patch

`apps/api/app/attack/citations.py` states an invariant at line 18 — _"Every rule
here either finds EXACTLY ONE candidate or gives up"_ — that **has never held**.
Two consecutive patches each looked done and each was wrong, both found only by
adversarial audit. Part 5 lists four surviving wrong-attribution paths and Part
5.1 settles how an uncertain resolution is allowed to affect a client-facing
coverage number. Read 5.1 before writing any code: the short version is that a
citation the resolver had to _change_ is an inference, inference is not
confirmation, and unconfirmed evidence earns no score and gets its own visible
state rather than being collapsed into `gap`.

---

# Show (and send) what actually feeds the ATT&CK mapping

## Context

An admin opening the MITRE ATT&CK workspace cannot see what the mapping will run
against. The page reports only a number — `23 tools available for mapping` —
after the run. There is a "Preview what will be sent" button, but it dumps the
raw payload as JSON into a scroll box, and for ATT&CK that payload carries all
633 technique codes, so the capability list is buried.

That blindness has already cost a real assessment. On 2026-08-07 a run executed
with `tools_available: 0` and wrote **607 fabricated gaps** across 633
techniques — a catastrophic-looking security posture that was purely an artifact
of no inventory being loaded (N-033). A hard block now refuses that run, but the
admin still cannot answer "what is being reviewed, and where did it come from?"

While researching this, a second and larger problem surfaced: **the model
receives only bare tool names.** The Tech Debt extractor already produces
`vendor`, `category`, `function` and — most importantly — `security_functions`,
its own prevent/detect/respond classification. All of it is discarded. The
pipeline computes "Falcon does detect + respond", throws it away, sends the
string `"crowdstrike falcon"`, and asks the model to re-derive detection /
prevention / response from the name alone.

So this change has two halves, both agreed in planning:

- **(A) Visibility** — show the capabilities being sent, with their source
  documents, before the run.
- **(B) Enrichment** — send the structured fields that already exist instead of
  bare strings.

Outcome: an admin can see and verify the mapping's inputs, and the model gets a
materially better hook to map from.

---

## Decisions taken

| Question            | Decision                                                  |
| ------------------- | --------------------------------------------------------- |
| Display or payload? | **Both.** The enrichment is the higher-value half.        |
| Multi-list scope    | **Surface, do not fix.** See below.                       |
| Screen space        | Summary always visible; line-by-line behind a disclosure. |

### The multi-list finding — surfaced, deliberately not fixed

`_client_tool_names` (`apps/api/app/routes/attack.py:450`) unions **every
non-discarded capability list version across every Tech Debt service for the
client**. Superseded v1 and v2 both contribute. Its own docstring calls this
"arguably wrong but pre-existing".

This plan **displays that honestly** (naming each contributing list and version)
and **changes no filtering**. Restricting to the latest approved list would
silently alter what every existing ATT&CK assessment maps against — that is a
behaviour change deserving its own PR, its own tests, and a deliberate decision.

---

## Implementation

### 1. Backend — a structured capability record

Replace the bare-name query with one that carries provenance.

**`apps/api/app/routes/attack.py`**

- Add a frozen dataclass `CapabilityInput` (name, vendor, category,
  `security_functions`, `list_id`, `list_version`, `service_id`,
  `source_artifact_id`, `awaiting_signoff`).
- Add `_client_capability_inputs(db, client_id) -> list[CapabilityInput]`
  selecting whole `CapabilityItem` rows joined to `CapabilityList` and `Service`,
  using the **existing** `security_scope_filter()` from
  `apps/api/app/tech_debt/security_scope.py` — do not reimplement the rule.
- Keep `_client_tool_names` as a thin wrapper (`sorted({c.name ...})`) so
  `valid_tools` and existing callers are untouched.

**Dedup rule:** items are currently deduped by name. Keep that for `valid_tools`,
but retain every contributing row for display — the same tool appearing in two
lists is exactly what the admin needs to see.

### 2. Backend — the enriched payload

In `build_attack_ai_request` (`attack.py:517`), change `inputs["capability_list"]`
from `list[str]` to a list of objects:

```json
{
  "name": "CrowdStrike Falcon",
  "vendor": "CrowdStrike",
  "category": "EDR",
  "security_functions": ["detect", "respond"]
}
```

Only these four fields egress. **No cost, no licence count, no ids** — they are
irrelevant to mapping and the redactor should not have to reason about them.

`valid_tools` stays `frozenset(name.lower())`, so `_validate_tools`
(`attack.py:759`) is unchanged and the hard allow-list still holds.

**Update `_MITRE_MAP_PROMPT`** (`apps/api/app/ai/jobs.py:89`) — it currently says
"You may ONLY name tools that appear in the supplied capability list". It must
say to cite the `name` field, and that `security_functions` is the extractor's
own prevent/detect/respond finding to be used as evidence, not gospel.

### 3. Must-fix: the fixture will silently break

`_fixture_mitre_map` (`apps/api/app/ai/fixtures.py:101`) calls
`_strs(payload.get("capability_list"))`, and `_strs` (line 90) keeps only
`isinstance(v, str)`. Objects would be dropped to `[]`, so **fixture mode would
cite zero tools** — and fixture mode is what CI runs. Every existing assertion
about tool citations (e.g. `s5-attack`) would fail.

Update the fixture to read `name` from either shape (string or object). This is
the single highest-risk item in the change.

### 4. Backend — a read endpoint for the admin view

`GET /attack/services/{service_id}/ai-inputs` in `attack.py`, admin-only,
tenant-scoped via the existing `require_service_in_tenant`.

Returns (new schema in `apps/api/app/schemas/attack.py`, all fields additive):

- `capabilities[]` — name, vendor, category, security_functions,
  `awaiting_signoff`, `source_list_version`, `source_document` (`{id, title}` or
  null)
- `sources[]` — the contributing lists: `{list_id, version, status, service_id,
documents: [{id, title}]}`
- `excluded[]` — from `CapabilityList.excluded_rows`, with `summary` +
  `confirmed`
- `not_sent[]` — items filtered out by security scope (`security_related is
False AND security_class_confirmed`), so the admin can spot a misclassification
- `totals` — `{sent, excluded_at_extraction, filtered_non_security}`

**Deliberately a separate endpoint, not `/ai/preview`.** The preview costs a
rate-limit slot, requires an existing assessment, and returns a redacted blob;
this is a cheap read the page can load on mount.

### 5. Backend — resolving source documents

`CapabilityList` has **no artifact link**; only `CapabilityItem.source_artifact_id`
does, and rows recovered via `include_excluded_row`
(`apps/api/app/routes/tech_debt.py:393`) are created with **NULL** provenance.

Resolve per item, collect the distinct non-null artifact ids per list, and batch
one query against `Artifact` for titles. Where an item has no artifact, say so
("added by hand") rather than inventing a source. **No migration in this change**
— adding `CapabilityList.source_artifact_id` is a follow-up, and the backfill
data already exists in the `capability_list.extracted` audit rows.

### 6. Frontend — `AttackAiInputsPanel`

New `apps/web/src/components/admin/attack/AttackAiInputsPanel.tsx`, mounted
inside the existing `<WorkflowStep number={1} …>` in `AttackWorkspace.tsx`,
above the Run AI button.

Collapsed (always visible, ~3 lines):

```
Mapping against 23 security capabilities
from 2 Tech Debt lists · 8 rows not sent            [show all ▾]
Source: Enterprise_Inventory.xlsx, Q3_Additions.csv    [Download]
```

Expanded: a table of name / vendor / category / D-P-R / source document /
list version, then the two "not sent" groups with their reasons.

- **Zero capabilities must be loud**, not a quiet "0" — it is the N-033 signal.
- Reuse the download-link pattern from
  `apps/web/src/components/admin/IntakeDocumentsPanel.tsx`
  (`/api/proxy/artifacts/{id}/download`) rather than inventing one.
- Client wrapper in `apps/web/src/lib/attack/client.ts`, following the existing
  read-body-once error handling in that file.

### 7. Cost note

The capability list is sent to **every batch** (~26 for a full matrix), so
enrichment multiplies its input tokens by the batch count. For ~25 tools that is
roughly 7k → 28k input tokens per run — around **$0.30 at Opus rates**, against
a run whose output already costs ~$6. Acceptable, but state it in the PR.

---

## Test plan (TDD — tests first at each layer)

**Backend unit** (`apps/api/tests/unit/test_attack_run_ai.py`, extending the
existing `_seed_tech_debt_tools` helper which already supports
`security_related` / `confirmed`):

- the payload carries objects with vendor/category/security_functions
- `valid_tools` still validates, and an invented tool is still dropped
- a confirmed non-security row is absent from the payload but present in
  `not_sent`
- the empty-capability 409 guard still fires

**Fixture** (`test_llm_*` or a new case): `_fixture_mitre_map` cites tools when
given objects — the regression that would otherwise break CI silently.

**New endpoint**: admin-only (403 for client role), tenant-scoped, resolves
document titles, reports items with NULL `source_artifact_id` without inventing
a source, and lists multiple contributing lists.

**Web unit** (`AttackAiInputsPanel.test.tsx`): collapsed summary counts,
expansion reveals rows, zero-capability state is prominent, multiple sources
render, a NULL-provenance row is labelled rather than blank.

**E2E** (`e2e/smoke/s5-attack.spec.ts`): the panel renders before Run AI and its
count matches `tools_available` in the run response.

## Verification

1. `docker compose exec -T api pytest -m unit -q`
2. `docker compose exec -T web sh -lc "cd /app && pnpm -F web exec tsc --noEmit && pnpm -F web lint && pnpm -F web test"`
3. `docker compose exec -T api sh -lc "cd /app && ruff check --no-cache . && black --check ."`
4. Prettier at the pinned 3.9.5 from repo root
5. `docker compose up -d --force-recreate web`, then drive the ATT&CK workspace
   in a browser against the "Testing" client (which has a 45-item approved list)
   and confirm the panel matches the database
6. `cd e2e && npx playwright test smoke/s5-attack.spec.ts` — **check
   `SHIELD_LLM_MODE` first**; this stack runs live, where `mitre_map` takes ~10
   minutes and spends real money

## Risks

| Risk                                             | Mitigation                                                                                                                                                                                                                                                                                                                   |
| ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Fixture silently returns no tools, breaking CI   | Handle both shapes; test it first                                                                                                                                                                                                                                                                                            |
| Enrichment changes mapping quality unpredictably | Only a live run can judge; ship behind no flag but state it in the PR and re-check the Phase 5 dataset traps                                                                                                                                                                                                                 |
| Redaction sees a new payload shape               | **Verified safe** — `redact_payload` (`apps/api/app/ai/redact.py:250`) already recurses through Mappings and lists and redacts only string values, not keys. Still add a preview test pinning it. Minor edge case: a vendor name matching the client's org name would be redacted, which is the redactor working as intended |
| Panel adds length to an already-long page        | Collapsed by default; three lines at rest                                                                                                                                                                                                                                                                                    |

## Explicitly out of scope

- **Fixing** the multi-list union (surfaced only — behaviour change, own PR)
- `CapabilityList.source_artifact_id` migration + audit-log backfill
- Repairing `AiPreviewButton`'s broken error text (`payload.error.message` vs
  FastAPI's `detail`) — real, unrelated, worth its own fix
- Persisting the exact tool set used by a past run (audit stores only a count)

---

# PART 2 — Workspace redesign (approved 2026-08-08, NOT started)

Read this whole section before writing code. The constraint in §2.2 is the one
that must not be lost.

## What the owner asked for

> "remove step 3 the approve because it doesn't seem to serve a purpose, retool
> step 4 so that we can view the draft documents and be able to make any edits
> and allow the AI run again. same for step 1 there should be a way to edit the
> inputs received from the Tech debt... I'd prefer a pop up window for step one
> to allow the edit and a pop up window that allows the edit after the AI run...
> then the final step is to release the documents to the client."

Target flow:

```
Step 1  Review + EDIT inputs from Tech Debt      [modal]
Step 2  Run AI
Step 3  Review + EDIT results, preview documents [modal] [re-run AI]
Step 4  Release to the client portal
```

## 2.1 Approve is NOT ceremony — three things depend on it

Verified in code, do not delete it blindly:

| Depends on APPROVED                                                | Evidence                                                                                |
| ------------------------------------------------------------------ | --------------------------------------------------------------------------------------- |
| Deliverable finalize is hard-gated                                 | `attack.py:1416-1422`, and identically `csf.py:1787`, `zt.py:1262`, `tech_debt.py:1077` |
| The matrix locks so scores cannot shift under a generated document | `build_attack_ai_request` raises 409 "This assessment is locked"                        |
| Release -> client visibility                                       | `clients.py` — "A released deliverable's assessment is APPROVED/RELEASED"               |

The decision was **fold it into the flow, not delete it**: the freeze still
happens, it just stops being a step whose only visible effect is enabling
another button.

## 2.2 THE WATERMARKING CONSTRAINT — read this before slice 2

**Today no document can be generated from an unapproved assessment.** All four
services (attack, csf, zt, tech_debt) hard-gate finalize on APPROVED/RELEASED,
and nothing else in the codebase calls `render_pdf` / `render_xlsx` /
`render_docx` (grepped: no callers outside those route modules).

**Slice 2 deliberately relaxes that gate** so an admin can preview draft
documents before releasing. The moment it does, the system can produce a
real-looking PDF from a still-editable assessment.

**Therefore: slice 2 MUST ship DRAFT watermarking in the same change as the
relaxed gate. Never one without the other.**

Why this is non-negotiable rather than nice-to-have: this codebase has already
shipped a formal client deliverable that stated "Total annual cost: $3,368,000"
for a $3,608,000 upload with no disclosure (N-010, fixed in `5e1f075`). A
document that looks final and is not is precisely the failure mode this product
has already committed once. An unwatermarked draft PDF is a new way to hand
someone an unreleased report.

**Exception to know about: the Risk Register.** `POST
/risk/clients/{cid}/register/export` (`routes/risk.py`) has NO approval gate at
all — there is no approved state on a register; the model is generate -> export.
It is admin-only, and the client dashboard is gated on `finalized_at`, so no
UNAPPROVED document reaches a client. But it reaches one with no approval step,
because none exists. Risk Register therefore needs its watermarking decision
made explicitly; it does not inherit the other four services' guarantee.

## 2.3 Slice 1 — RESHAPED, and why

The original plan was "one atomic publish = approve + finalize + release".
**That is unsafe and must not be built.**

Finalize and Release are ALREADY separate actions today
(`AttackDeliverableCard.tsx` — `onFinalize` at :69, `onRelease` at :87;
`deliverable_release.py:68` requires `finalized_at is not None`). A deliverable
sits in "Finalized vN" with `released_at` NULL, admin-visible and marked not
client-visible — `s40-admin-deliverables` tests exactly that state.

That is a REVIEW WINDOW: generate -> inspect the real document -> decide to
release. Collapsing all three into one action deletes it, so an admin would go
from editing the matrix to the client holding the report in a single click. That
is worse than today and the opposite of what was asked for.

**Slice 1 as it should be built:**

- Generating the documents IMPLICITLY freezes the assessment (the approve call
  happens inside finalize). Approve disappears as a step; nothing is ever
  rendered from unfrozen state.
- Release stays a SEPARATE, final action. The review window survives.
- No watermarking needed in slice 1, because every document still corresponds to
  a frozen assessment.

Safe to ship standalone on that shape. Not on the atomic-publish shape.

## 2.4 Remaining slices

- **Slice 2** — draft previews from an unfrozen assessment + DRAFT watermarking
  (see §2.2 — same change, always). Also needs a way to re-open a frozen
  assessment, since "preview -> edit -> re-run" otherwise dead-ends: approve
  currently locks run-ai out.
- **Slice 3** — the two edit modals (inputs from Tech Debt; results after the
  run). `Modal` exists in `@shield/design-system`. Additive, no integrity impact.
- **Slice 4** — restructure the ATT&CK workspace to the 4-step flow, then roll
  out to Tech Debt / CSF / Zero Trust. `WorkflowStep` is already shared at
  `apps/web/src/components/admin/WorkflowStep.tsx`.

## 2.5 Context a fresh session will not have

- ATT&CK already has numbered steps (`WorkflowStep`), added 2026-08-08.
- `GET /attack/services/{id}/ai-inputs` + `AttackAiInputsPanel` already show
  what feeds the mapping; the step-1 edit modal should extend that panel rather
  than invent a second surface.
- The ATT&CK allow-list accepts only APPROVED/RELEASED capability lists as of
  2026-08-08; drafts are reported via `draft_excluded_count`, never silently
  dropped.
- Citations are resolved by `app/attack/citations.py`, not exact-matched.
  `citations_normalized` / `citations_rejected` ride the run response.
- Gates: `pytest -m unit` (854 passing), `pnpm -F web test` (149), plus ruff,
  black, tsc, eslint, and prettier at the pinned 3.9.5.
- Do NOT restart the api container while a detached pytest run is in flight — it
  kills the run (done three times in one session).
- This stack runs `SHIELD_LLM_MODE=live`. Check the mode before running e2e
  locally; a stray spec spends real money.

---

# PART 3 — Reopen + release-staleness guard (four services)

**This supersedes the "slice 1" shape in Part 2 §2.3.** Investigation on
2026-08-08 found a dead end and a real integrity gap that must be fixed before
freeze-on-generate is safe. Read this whole part before writing code.

## 3.1 The dead end that forced this

Once an ATT&CK assessment is APPROVED there is NO repair path. Verified:

| Action                 | Result once APPROVED                                 | Evidence                             |
| ---------------------- | ---------------------------------------------------- | ------------------------------------ |
| Edit a coverage row    | 409 "This assessment is locked"                      | `attack.py:389-397`                  |
| Re-run AI              | 409 "This assessment is locked"                      | `build_attack_ai_request`            |
| Discard the assessment | 409 — discard accepts DRAFT only                     | `attack.py:1067`                     |
| Unapprove / reopen     | **no endpoint exists**                               | grepped                              |
| Start over             | mints a new version with **633 fresh unscored rows** | `create_assessment`, `attack.py:300` |

So an admin who generates a deliverable and spots a mistake must throw away the
whole assessment and pay for another live AI run (~$6 + hours of curation).

This trap exists TODAY. It becomes far worse under freeze-on-generate, because
freezing stops being a deliberate click and becomes a side effect of the REVIEW
action — exactly what an admin does when they want to LOOK at something.

**Therefore: build reopen FIRST, then freeze-on-generate. Never the reverse.**

## 3.2 The reopen contract

`POST /{service}/assessments/{assessment_id}/reopen` — admin only, tenant-scoped.

- APPROVED -> DRAFT
- Sets `documents_stale = True` (the flag already exists; see §3.4)
- Idempotent on an already-DRAFT assessment (mirrors discard, which is
  idempotent on already-discarded)
- **REFUSED with typed 409 once any deliverable for that service has
  `released_at IS NOT NULL`**
- Writes an audit row

**Tests are already written** at `apps/api/tests/unit/test_attack_reopen.py`
(7 cases, ATT&CK only). They are RED — the endpoint does not exist yet. That
file is uncommitted; either implement against it or delete it, but do not leave
it red in a commit.

### 3.3 Why the guard keys on `released_at`, NOT assessment status

**This is the single most important detail in Part 3.**

Nothing in the ATT&CK routes ever assigns `AttackAssessmentStatus.RELEASED`. The
only status write is `a.status = APPROVED` (`attack.py:1034`). Releasing sets
`released_at` on the **deliverable**, via the shared `release_deliverable()`.

So a reopen guard written as `if assessment.status == RELEASED: refuse` would
**never fire**, and would cheerfully reopen an assessment whose report is already
with the client. The scores could then change while the delivered PDF says
otherwise — the report would describe a state that no longer exists anywhere.

Guard on the deliverable:

```python
released = db.execute(
    select(Deliverable.id).where(
        Deliverable.service_id == svc.id,
        Deliverable.released_at.is_not(None),
    ).limit(1)
).first()
if released is not None:
    raise HTTPException(409, detail={"reason": "already_released", "message": ...})
```

Once a document has gone out, the assessment behind it stays frozen forever.
That is the point-in-time guarantee a client-facing report rests on.

## 3.4 The release-staleness guard — shared, and currently ABSENT

`deliverable_release.py` performs **no staleness check whatsoever**. A stale
document can be released today, in all four services. `StaleDocsNudge` in the UI
is advisory only.

This is latent today (you cannot edit after approving, so staleness rarely
survives to release) but **reopen makes it real**: reopen -> edit -> the
generated document no longer matches -> nothing stops the release. The guard
must therefore land in the SAME change as reopen.

**Location: `apps/api/app/deliverable_release.py`** — all four services call
`release_deliverable()` (`attack.py:1586`, `csf.py:1965`, `zt.py:1445`,
`tech_debt.py:1241`), so one guard covers all four. It needs the parent's
staleness, which differs per service kind, so pass it in from the caller rather
than teaching the shared helper about four models.

### The message must explain, not just refuse

A bare 409 is the same silent-failure shape this whole engagement has been
fixing, moved one layer over. Use the D-016 `{reason, message}` dict-detail:

```python
detail={
    "reason": "documents_stale",
    "message": (
        "This assessment changed after the document was generated. "
        "Regenerate the deliverable before releasing it."
    ),
}
```

That remedy is genuinely actionable: finalize CLEARS `documents_stale`
(`attack.py:1541`, `csf.py:1694` and `:1920`, `zt.py:1395`), so "regenerate"
really does unblock the release rather than dead-ending.

## 3.5 Four-service scope

| Service    | `documents_stale`?                     | Reopen endpoint | Notes                       |
| ---------- | -------------------------------------- | --------------- | --------------------------- |
| ATT&CK     | yes (`models/attack_assessment.py:61`) | needed          | tests already written       |
| NIST CSF   | yes (`models/csf_assessment.py:76`)    | needed          | own status enum             |
| Zero Trust | yes (`models/zt_assessment.py:73`)     | needed          | own status enum             |
| Tech Debt  | **NO**                                 | needed          | **see the exception below** |

**Reopen cannot be shared** — each service has its own assessment model and
status enum — so it is four endpoints following one pattern. The release guard
IS shared.

### The Tech Debt exception

Tech Debt has no assessment and no `documents_stale`. It freezes on
`CapabilityListStatus.APPROVED` (`tech_debt.py:1077`), and its deliverable is
generated from the capability list.

So Tech Debt needs an explicit decision, NOT an inherited rule:

- either add a staleness notion to `CapabilityList` (a `documents_stale` column,
  set when an item is edited after approval), or
- exempt it from the shared guard deliberately and record why.

Do not let it fall through silently — an unstated exemption is how the ATT&CK
allow-list ended up accepting draft lists for months.

## 3.6 History is KEPT, not deleted — confirmed consistent

Reopen must NOT delete or mutate the now-stale deliverable. `Deliverable` carries
`version` and `superseded_by`, and finalize computes
`next_version = len(existing) + 1` — it adds a new version alongside the prior
one and never mutates it. Reopening therefore leaves the stale document in place
as history; the next generation supersedes it.

This matches the codebase's append-only / audit-spine pattern rather than being a
one-off exception. Confirmed by reading `models/deliverable.py` and the finalize
body, not assumed.

## 3.7 Build order

1. Reopen for ATT&CK, against the existing test file. (RED -> GREEN)
2. Shared release-staleness guard + typed message, with tests.
3. Tech Debt decision (§3.5) — resolve explicitly before rolling out.
4. Reopen for CSF and ZT, same pattern.
5. ONLY THEN freeze-on-generate (Part 2 §2.3), which is now safe because a
   mistake costs one click.
6. Then the edit modals and workspace restructure (Part 2 §2.4).

---

# PART 4 — HANDOFF (written 2026-08-08, context exhausted)

## Do this first

**PR #29 is GREEN in CI but MUST NOT MERGE.** An adversarial audit found 13
defects the suite does not catch. Full write-up: **GitHub issue #30**. Read it
before touching anything.

### The two blockers, both mine

**Blocker 1 — `apps/api/app/attack/citations.py:94-101`.** Rule 3 (substring)
runs before rule 4 (vendor) and never consults the vendor index, so an ambiguous
vendor citation resolves to the WRONG product instead of refusing. Reproduce:

```python
from app.attack.citations import Candidate, CitationResolver as R
R([Candidate('Cisco Umbrella','Cisco'), Candidate('Duo Security','Cisco')]).resolve('Cisco')
# -> ('Cisco Umbrella', True)   # should be (None, False)
```

Cited as prevention for T1110 Brute Force this credits a DNS filter with MFA,
and it is counted as `citations_normalized` — logged as a SUCCESS.

Fix: check vendor ambiguity BEFORE rule 3, or make rule 3 refuse when
`self._vendors.get(key)` has >1 member.

**The existing test cannot catch it.** `test_an_ambiguous_vendor_is_refused`
(`tests/unit/test_attack_citations.py:83-88`) uses two candidates that BOTH
contain "Splunk", so rule 3 refuses and rule 4 never runs. Change one candidate
to `Phantom SOAR` and watch it fail FIRST, then fix.

**Blocker 3 — `citations_rejected` / `citations_normalized` never reach the UI.**
Grep confirms they appear nowhere in `apps/web/src`; `AttackRunAiResponse` in
`apps/web/src/lib/attack/types.ts:81` lacks both fields. The backstop is
invisible to the consultant. Surface them in the run summary in
`AttackWorkspace.tsx` (near the existing "Updated N fields" line).

### Then

**A fresh adversarial audit is MANDATORY before merging — the owner was explicit
that it is not optional.** `.claude/agents/adversarial-reviewer.md` is committed
and will be a real `subagent_type` in a new session (the registry loads at
startup, which is why this run had to inline it into `Explore`).

## Order of work

1. Fix blockers 1 and 3, fail-first.
2. Re-run the adversarial audit against the branch.
3. Merge PR #29 only if that comes back clean.
4. Then CHANGELOG + CONTEXT.md for #29's work and a `v3.12.0` tag — **v3.11.0
   predates all of it**, so the current release does not contain the enrichment,
   resolver, `/ai-inputs` panel or draft exclusion.
5. Then Part 3 (reopen x4 + shared release-staleness guard + the Tech Debt
   decision). Entry point: `tests/unit/test_attack_reopen.py`, 7 tests already
   committed as `xfail(strict=True)` — they flip to failures the moment the
   endpoint lands, forcing the marker off.
6. Then Part 2 (freeze-on-generate, edit modals, draft watermarking, restructure,
   rollout).

## Findings NOT to lose (full detail in issue #30)

- **#2** the draft exclusion re-opens N-033 in a new shape: a stale 3-tool
  approved list + a current 25-tool draft runs silently against 3. Only ZERO
  tools 409s.
- **#9** approval is a SNAPSHOT, not a lock — an APPROVED capability list is
  still mutable, so rows can enter the allow-list after the human vouched.
- **#5** a tool whose name contains the client org name is redacted on egress but
  not on resolution, so it is permanently uncitable on every run.
- **#4** the panel does not render before an assessment exists, contradicting the
  endpoint's own stated reason for existing.
- **#6** `draft_excluded_count` over-counts (no set-difference against in-scope).
- **#8** `CapabilityListStatus.RELEASED` is never assigned anywhere; a test
  verifies a state the app cannot produce.

## Confirmed separately: N-019 is real

Queried live: `COMPLETED` 291 rows all with tokens; `FAILED` 3 rows with **0**
input tokens, **0** output tokens, 3 with duration. Failed calls ARE recorded —
tokens specifically are dropped on the failure branch. Two of those failures
logged `charged_likely: true`, so the money was spent and the ledger says zero.

## Environment

- Working tree clean apart from `.playwright-mcp/` (scratch, NEVER commit).
- On branch `feat/attack-ai-inputs-visibility` at `2bbb00a`, not main.
- Stack is `SHIELD_LLM_MODE=live` with a real key — check before running e2e.
  ~$12 spent today.
- Do NOT restart the api container while a detached pytest run is in flight.
- Local suite: 861 tests, 0 failures, 7 xfailed. Web: 149.

---

# PART 5 — CITATION RESOLVER REWRITE (the actual next task)

## Status corrections — read before trusting any earlier summary

| Finding                        | Earlier claim        | ACTUAL status                                                                                                                                                                                                                   |
| ------------------------------ | -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| #1 vendor ambiguity            | "fixed" in `68565c2` | **PARTIAL.** Three wrong-attribution paths survive. See issue #30 re-audit comment.                                                                                                                                             |
| #3 surface the counts          | "fixed"              | **IN PROGRESS, not done.** The render has NO test — `AttackWorkspace.test.tsx` never sets a `runResult`, and `data-testid="attack-citations-rejected"` is referenced nowhere. And surfacing the counter made #11 worse (below). |
| #11 punctuation false-positive | "low, deferred"      | **PRIORITY BUMPED.** It stopped being deferrable the moment it became user-visible.                                                                                                                                             |

**#11 in detail.** `citations.py:93` — `return name, _fold(name) != cited.strip().casefold()` — folds the left side and not the right, so a VERBATIM exact citation of any punctuated name is reported as normalised: `Tenable.io`, `AT&T Cybersecurity`, `F5 BIG-IP`. It was harmless as log noise. `68565c2` now prints "N citations were resolved from a near miss" in the run summary, so a client with punctuation in a tool name sees a permanently non-zero near-miss count with zero near misses — a false statement a consultant can act on. Fix it in the rewrite; do not ship the surfaced counter without it.

## This needs a REWRITE, not a third patch

Two patches in a row each looked done and each was wrong, both in `resolve()`, both found only by adversarial audit while CI stayed green. The module's stated invariant at `citations.py:18` — _"Every rule here either finds EXACTLY ONE candidate or gives up"_ — **has never actually held**. Rewrite against that invariant rather than adding a third rule.

Known-broken paths the rewrite must close (all verified live, issue #30):

1. Guard keyed on nullable `vendor` — one blank vendor and the original bug returns.
2. Name-vs-vendor cross ambiguity unchecked (`VMware Carbon Black` v:Broadcom + `Workspace ONE` v:VMware, cite "VMware" -> Carbon Black).
3. Substring rule does not refuse on 2+ matches; it falls through to rule 4, which resolves anyway.
4. #11 above.

2 and 3 are mechanically fixable (union the candidate sets; refuse when `len(subs) > 1`). 1 is the design problem below.

## The tri-state decision — DO NOT pick either end

The trade as originally framed was a false binary:

- **Refuse whenever any candidate has a blank vendor** — too blunt. Kills good rescues along with bad ones; the live run measured 260 legitimate rescues, and most real capability lists have incomplete vendor data.
- **Resolve confidently as it does now** — risks exactly the wrong-attribution failure the whole feature exists to prevent, and counts it as a success.

**Build a third outcome instead.** When a resolution depends on incomplete data — a blank/missing vendor, a name-vs-vendor cross, any case where uniqueness cannot be established from the data present — do not refuse and do not resolve confidently. Return **resolved-but-needs-review**: apply the citation, mark it, and surface it as its own count distinct from both `citations_normalized` and `citations_rejected`.

This is the same shape as `confidence_pct` on the Tech Debt side: the system states what it inferred AND how sure it is, rather than collapsing an uncertain answer into a confident one. A consultant can then review a short list instead of either trusting a silent guess or losing the citation entirely.

**If the rewrite ends up having to choose between recall and accuracy with no gray zone available, choose ACCURACY.** A dropped citation is counted and visible. A wrong attribution is invisible and reaches the client.

## Handoff state

- Branch `feat/attack-ai-inputs-visibility` at `68565c2`. CI green, 862 backend / 149 web, 0 failures, 7 xfailed — which is exactly the "green means nothing" state that let both defects through.
- **PR #29 does NOT merge** until the rewrite lands and a fresh adversarial audit comes back clean.
- Issues: **#30** both audits, **#31** finding 2 deferred with risk, **#32** finding 9 deferred with risk, **#33** findings 4/5/6 + lower-severity set.
- Waiting on the rewrite, in order: merge PR #29, CHANGELOG + CONTEXT.md describing what actually landed (enrichment, citation resolver, `/ai-inputs` panel, draft exclusion) and stating explicitly that **Part 2 and Part 3 have NOT shipped**, tag `v3.12.0`, then design the automatic pre-merge adversarial audit (CI job on PRs is the only mechanism that binds everyone; a local hook does not).
- `.claude/agents/adversarial-reviewer.md` is committed and becomes a real `subagent_type` in a new session.

## 5.1 Resolved-but-needs-review MUST NOT feed the computed score

The Part 5 wording — _"apply the citation, mark it, count it separately"_ — was
ambiguous and, read literally, it defeats the accuracy tiebreak it sits next to.
An applied-but-unreviewed citation is baked into the report's coverage number
before any human looks at it, which is exactly the silent wrong-attribution this
whole feature exists to prevent. Resolve the ambiguity as follows.

**Rule: a resolution that depends on incomplete data does not contribute to the
computed coverage score until a human clears it. For scoring purposes it is
treated as if it were rejected. It is NOT dropped — it is retained, visible, and
queued for review.**

Rejected = invisible and gone. Flagged = visible and retained, but earns no
score. That distinction is the whole point.

### The enforcement point is the technique STATUS, not the citation count

This is the detail that makes the rule non-obvious. Coverage % is
`(covered + 0.5 x partial) / addressable x 100`, computed from each technique's
`status` — see `app/attack/analytics.py` and confirm before implementing. The
citations populate `detection_tools` / `prevention_tools` / `response_tools`;
they do not themselves compute the percentage.

So marking a citation "needs review" changes NOTHING about the score on its own.
The model already returned `status: covered` in the same response, and that
status is what scores. **The rewrite must therefore decide what a technique is
worth when its supporting citations are all unreviewed**, and the answer that
honours the tiebreak is: it does not count as covered or partial until cleared.

### THE RULE (decided 2026-08-08 — do not re-litigate)

**A technique's status counts toward the score only when it is backed by a
CONFIRMED citation — not merely a resolved one, and not a flagged one. A
technique whose support is unconfirmed gets its OWN visible state. It is never
collapsed into `gap`.**

Scoring as `gap` was considered and is **REJECTED**. Gap and pending-review mean
different things to a consultant: gap says _nothing was found_, pending-review
says _something was found but is not confirmed yet_. Collapsing the second into
the first is a false negative dressed as a finding — the mirror image of the
false positive this whole rule exists to stop, and it would send a consultant
hunting for a control the client already owns.

So there are FOUR client-facing states, not three: covered / partial / gap /
**pending review**, plus the existing `not_applicable` and `unscored`.

### What "confirmed" means — the line, drawn explicitly

A citation is CONFIRMED when either:

- **it required no inference** — the model cited a name that matches an approved
  capability exactly (after case/whitespace normalisation only), so there is
  nothing to be wrong about; or
- **a human cleared it** in the review queue.

A citation the resolver had to _change_ to make match — every near-miss
normalisation, every vendor resolution — is an INFERENCE, and inference is not
confirmation however plausible it looks. Those are `pending review` until a
human clears them.

Scope check against the live run so this is not sized blind: that run reported
295 rescued citations. Those 295 become the initial review queue — bounded and
walkable. It does NOT put all 633 techniques in review, because exact citations
are confirmed on arrival and most citations are exact.

**This line is OWNER-CONFIRMED (2026-08-08), not an implementer's judgment
call.** The alternative was put to the owner explicitly and rejected: the wider
reading — nothing confirmed without a human, including exact matches — reports
0% coverage on every fresh run until a consultant walks all 633 techniques. The
narrow line above is the decision. Do not re-open it as a design question during
the rewrite; if it genuinely needs to move, that is a new decision to take to
the owner out loud, not a refactor.

### Do NOT reuse the existing `unscored` bucket

`analytics.py:88-92` already computes `addressable = covered + partial + gap`
and keeps `unscored` outside both numerator and denominator — so the exclusion
mechanism it needs already exists and is verified working.

**But `pending_review` must be its own field, not folded into `unscored`.**
`unscored` today means "no human or model has assigned a status." Pending-review
means "a status exists and its evidence is unconfirmed." Reusing the bucket
would give both meanings one number and one label, which is the exact
conflation this section rejects, just moved down a layer. Add the field to
`CoverageCounts` / `TacticCoverage` and render it distinctly.

### Invariants to test

1. A run whose citations are ALL flagged produces a coverage percentage no
   higher than the same run with those citations rejected.
2. A pending-review technique is NOT counted in `gap` — asserted on the number,
   not just on the rendered label.
3. Clearing a flagged citation moves its technique out of pending-review and
   into whichever of covered/partial/gap its status says, changing the
   percentage at that moment and not before.
4. `pending_review + covered + partial + gap + not_applicable + unscored`
   equals the total technique count. No row falls between states.

### A related defect the rewrite should confirm or close

A technique can currently read `covered` with EMPTY tool lists — when every
citation for it was dropped, the status survives untouched. That means the score
can already be inflated by citations that never validated, independently of the
tri-state work. Verify this against `analytics.py` and treat it as in scope: it
is the same failure (unsupported coverage inflating a client-facing number)
arriving by a different route.

### Why this is worth the recall it costs

It will lower reported coverage on lists with incomplete vendor data, and that is
the correct direction. An understated coverage number is a conservative claim a
consultant can raise after review; an overstated one is a false assurance already
delivered to a client. When the two conflict, the number that reaches the client
must be the one the evidence supports.
