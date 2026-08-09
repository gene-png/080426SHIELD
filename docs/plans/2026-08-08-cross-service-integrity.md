# Cross-service integrity plan — Tech Debt, CSF, Zero Trust, ATT&CK, Risk Register

**Written 2026-08-08.** Companion to `docs/plans/2026-08-08-attack-citation-resolver.md`
(PR #34), which is ATT&CK-only. That plan's findings are not ATT&CK defects that
happen to live in ATT&CK — they are one defect family, and it is present in all five
services. This plan names the family, lists every verified instance, and orders the
work.

**Verification basis.** Every `file:line` below was read on `main` at `15b8145`, not
on PR #29's branch. The ATT&CK plan's line numbers are #29-based and will not match.
Claims that depend on unmerged #29 code are marked **[#29]**.

**This document was adversarially audited before publication** (two independent
read-only passes). The audit falsified two of the first draft's load-bearing claims
and reversed one of its two recommendations. Both corrections are folded in below,
and §10 records what changed so the next reader can see the audit was not decorative.

---

## 1. The family

> **An AI-suggested value that fails validation is dropped silently, and the run's
> output is indistinguishable from a run where the model had nothing to say.**

Every service applies AI output through the same shape: iterate suggestions, look
each up against an authoritative key set, `continue` on anything that does not
match, commit the rest. The lookup failure is not counted and not returned. The
consultant sees "Updated N fields" and cannot distinguish N-of-N from N-of-600.

This is the shape that produced N-033 (607 fabricated gaps) and the wrong-tool
attribution in audit #30. Fixing the ATT&CK resolver does not fix it, because the
resolver is one of ten places it lives.

### Verified instances

| #   | Service       | Filter                                                       | `file:line` (main)                                                      | What is discarded                                                       | Counted?                    | Reaches UI?                                          |
| --- | ------------- | ------------------------------------------------------------ | ----------------------------------------------------------------------- | ----------------------------------------------------------------------- | --------------------------- | ---------------------------------------------------- |
| F1  | CSF           | `rows.get(f"{tier}\|{code}")` → `continue`                   | `csf.py:1474-1476`                                                      | The **entire** score suggestion for a key the model phrased differently | no                          | no                                                   |
| F2  | CSF           | `except (TypeError, ValueError): continue`, `if 0 <= v <= 2` | `csf.py:1479-1484`                                                      | One out-of-range/non-integer dimension score                            | no                          | no                                                   |
| F3  | ZT            | `rows.get(sugg.get("code"))` → `continue`                    | `zt.py:494-496`                                                         | The entire capability suggestion for an unknown code                    | no                          | no                                                   |
| F4  | ZT            | `_coerce` → `None` outside `1..max_stage`                    | `zt.py:469-474`, applied `:497-502`                                     | A maturity/target stage the model overshot                              | no                          | no                                                   |
| F5  | Risk          | `[t for t in linked_techniques if t in valid_techniques]`    | `risk.py:377-378`                                                       | A risk entry's ATT&CK / control traceability                            | no                          | no                                                   |
| F6  | Risk          | `_enum_or_none` → `tier = None`                              | `risk.py:373-376`, `:207-211`                                           | Likelihood/impact — entry lands **unscored and untiered**               | no                          | no                                                   |
| F7  | Risk + ATT&CK | `batches_failed`                                             | `risk.py:307/349/418`; `schemas/attack.py:124-125`, `attack.py:832-833` | Whole batches of entries                                                | **yes**, in the response    | **no** — neither string appears under `apps/web/src` |
| F8  | ATT&CK        | `_validate_tools`                                            | `attack.py:759-763`                                                     | Tool citations                                                          | no on `main`; **[#29]** yes | **[#29]**, and inaccurately (finding 11)             |
| F9  | ZT            | provenance stamped on a rejected suggestion                  | `zt.py:497-505`                                                         | _see below — not a drop but a lie_                                      | no                          | no                                                   |
| F10 | Risk          | `{...} or set(attack_all_codes())`                           | `risk.py:159`                                                           | _silently swaps the allow-list itself_                                  | no                          | no                                                   |
| —   | Tech Debt     | reconciliation                                               | `tech_debt.py:255-257`                                                  | Rows the extractor skipped                                              | **yes**                     | **yes** — `TechDebtWorkspace.tsx:529-537`            |

**Tech Debt is the reference implementation, not the exception.** It already ships
all three parts of the answer — a per-item confidence (`confidence_pct`), a count of
what was dropped (`source_rows_total`), an itemised list with reasons
(`excluded_rows`) — and a UI that renders them. This plan rolls out a pattern that
exists and works.

That comparison also sets the bar honestly: Tech Debt's banner is the one that broke
in the `source_rows_total > items.length` regression (its own comment at
`TechDebtWorkspace.tsx:518`). "We already have this pattern" does not mean copying
it is free.

### F9 and F10 in detail — the two that are not simple drops

**F9 — ZT stamps AI provenance on a suggestion it rejected.** `zt.py:503-505` sets
`answered_by` / `answered_at` / `answer_source = SOURCE_AI` **unconditionally**,
after `_coerce` may have rejected both values. `diff_keyed_rows` is passed only
`["maturity_stage", "target_stage"]` (`zt.py:509-511`), so the overwrite never
appears in the "what changed" list.

This is **live on `main` today**, not a hazard to watch for. `protected_keys` returns
`set()` when `is_fixture` is False (`ai/provenance.py:54-56`), so on a live run
nothing skips the row. Concretely: a client submits their ZT self-assessment
(`zt.py:881` stamps `SOURCE_CLIENT`); a consultant runs live AI; for one capability
the model returns stage 7 against a CISA max of 4; both writes are skipped; line 505
runs anyway. The row keeps the client's value and now claims `answer_source = 'ai'`.
The consultant sees an empty diff and a clean run. The `SOURCE_CLIENT` stamp is
unrecoverable — **and because `protected_keys` protects only non-AI rows, every
future fixture run is now free to overwrite that client's answer.**

`ai/provenance.py:40-45` documents this exact incident as already fixed: _"In the
2026-08-07 live run a client had answered 5 of 37 Zero Trust capabilities; a fixture
Run-AI changed three of the values and re-stamped all five `ai`, unrecoverably."_
Migration 0035 closed the fixture door. **`zt.py:505` leaves the live door open and
re-arms the fixture door behind it.** That is the "fix that breaks an earlier fix"
shape, and it ranks above most of W1.

Sibling, lower severity: `attack.py:782-783` stamps `answered_by`/`answered_at`
unconditionally on the same pattern (`AttackCoverage` has no `answer_source`).

**F10 — Risk silently swaps its allow-list for a different one.**

```python
# risk.py:159 — the docstring four lines up says
# "valid_techniques = every technique in the client's ATT&CK assessment"
valid_techniques = {r.technique_code for r in rows} or set(attack_all_codes())
```

Two silent branches. An ATT&CK assessment with zero coverage rows → the allow-list
becomes the **entire MITRE catalogue**, so `risk.py:377` stops meaning "assessed for
this client" and starts meaning "is a real technique id". No ATT&CK assessment at all
→ `valid_techniques` stays empty and **every** technique link on **every** entry is
dropped, with `batches_failed=0` and a clean-looking response. Same for
`valid_controls` when neither CSF nor ZT exists.

---

## 2. What does NOT generalise — and the one place the first draft got this wrong

The ATT&CK plan's **tri-state (confirmed / needs-review / rejected) does not transfer
to CSF, ZT, or Risk's key matching.** ATT&CK's uncertainty comes from fuzzy-matching
free text: the model writes a tool name and the resolver decides which approved
capability it meant, a decision that can be wrong while looking right. That is what
earns a needs-review state.

CSF, ZT and Risk match against **closed catalogues**, and the payload sends the model
the exact keys it will be matched against — `csf.py:1421-1422` ships
`sorted({r.tier})` and `sorted({r.subcategory_code})`; ZT ships its capability codes;
ATT&CK ships `technique_codes`. There is nothing to infer. **This claim was attacked
directly in audit and it held.**

**But the first draft over-applied the exemption.** Risk's **F6 is not a catalogue
lookup** — it is free-text → enum coercion, and the prompt actively instructs the
model to emit tokens the parser rejects:

- `ai/jobs.py:114-116` — prompt says `likelihood (Very Low..Very High)`,
  `impact (Negligible..Catastrophic)`
- `risk/engine.py:23-37` — the enum values are `very_low`, `very_high`,
  `negligible`, `catastrophic`
- `risk.py:207-211` — `_enum_or_none` does `enum_cls(value)`; `StrEnum` lookup is
  case- and separator-exact
- `risk.py:258-262` — the payload never sends the allowed tokens

So a model that obeys the prompt and returns `"likelihood": "High"` produces
`tier = None`. The entry is stored anyway. `clients.py:903-916` builds the 5×5 matrix
and tier bars only from entries that parsed, while `total_entries = len(entries)`
(`:929`) counts them all — **the client's Risk dashboard reports N open risks whose
matrix and tier bars sum to fewer than N, with no disclosure.**

**And a fixture can never see it.** `fixtures.py:308-309` emits the snake_case values
(`"very_high"`, `"catastrophic"`) that the parser accepts. There is a
`tests/unit/test_csf_ai_contract.py`, written after the identical CSF prompt/parser
drift recorded at `jobs.py:41-47`. **There is no Risk equivalent.** F6 is a live
prompt/parser contract drift, masked by the fixture, on the one service with no
review window (W6). It belongs in W1, not in "measure first".

**Still out of scope:** a CSF/ZT/Risk _code-format_ normaliser (`GV.OC-1` vs
`GV.OC-01`). That is a real near-miss class and exactly where a second resolver would
reintroduce the ATT&CK ambiguity risk. Count the misses first, then decide with data
— see the CI caveat in W1.

---

## 3. Cross-service map of the audit #30 findings

| Audit #30 finding                              | ATT&CK    | CSF                                 | ZT                   | Tech Debt             | Risk                                           |
| ---------------------------------------------- | --------- | ----------------------------------- | -------------------- | --------------------- | ---------------------------------------------- |
| 1 — wrong attribution from ambiguous match     | yes       | no (closed catalogue)               | no                   | n/a                   | no                                             |
| 3 — counters never reach the UI                | **[#29]** | yes (F1/F2, no counter at all)      | yes (F3/F4)          | **already solved**    | yes (F7 — counter exists, UI does not read it) |
| 9 — approval is not a lock                     | inherited | **YES — see W0**                    | no (`zt.py:697-706`) | **YES, the origin**   | no approval exists at all                      |
| 8 — guard keyed on a status no _route_ assigns | yes       | yes                                 | yes                  | yes                   | n/a                                            |
| Part 3 — no reopen path                        | yes       | yes                                 | yes                  | yes (different shape) | n/a                                            |
| Part 3 — release-staleness guard absent        | yes       | yes                                 | yes                  | yes                   | n/a — no release step                          |
| Part 2 §2.2 — draft watermarking               | yes       | **yes, and already producing them** | yes                  | yes                   | **yes, and already producing them**            |

The first draft put "CSF and ZT genuinely do lock on APPROVED" in this table, having
read one guard inside the _Run-AI builder_ and generalised. The audit falsified it.
ZT holds; **CSF does not**, and the hole is on the score table itself. That becomes
W0.

---

## 4. W0 — CSF scores are writable on a released assessment, with no audit row

**This was not in the ATT&CK plan, and it is the most severe thing this exercise
found. It goes first.**

`patch_dimension_score` — `csf.py:1045-1074`:

```python
row = db.get(CsfDimensionScore, score_id)
if row is None or row.client_id != client.id:
    raise HTTPException(404, ...)          # tenant only
data = body.model_dump(exclude_unset=True)
for f in ("governance","policy","implementation","monitoring","improvement",
          "in_scope","rationale","what_we_found","has_evidence","target_level","locked"):
    if f in data and data[f] is not None:
        setattr(row, f, data[f])
db.commit()
```

It never loads `CsfAssessment`, so it never sees its status. It can flip `locked`
itself. It emits **no `audit()` row**, unlike its sibling `patch_answer`
(`csf.py:535`). Two more CSF routes have the same gap: `upsert_gap_action`
(`csf.py:1241-1252`) and `seed_profiles` (`csf.py:954-1004`) check only `a is None`.

Contrast `csf.py:506-514` (`patch_answer`) and `zt.py:697-706`, which both refuse on
APPROVED/RELEASED/DISCARDED. This is not a house style — it is three routes that were
missed.

**Failure scenario.** CSF v3 is approved (`csf.py:696`), finalized (`csf.py:1787`
gate passes), released. The client downloads a PDF showing GV.OC-01 at Level 3. An
admin PATCHes `{"governance": 0, "policy": 0}` on that row. 200 OK.
`documents_stale` is not set — only run-AI sets it (`csf.py:1532`). The stored
assessment now disagrees with the released PDF, no audit row records who changed it,
and `clients.py:225` serves the altered numbers under a report the client already
holds.

**No test covers it.** `test_new_surface_authz.py:118-122` asserts tenant and role on
`dimension-scores`; nothing asserts 409-on-APPROVED. Green suite, open door.

**Fix:** load the parent assessment and apply the same APPROVED/RELEASED/DISCARDED
refusal `patch_answer` already uses, on all three routes; add the missing `audit()`
row; refuse rather than silently permit unlocking a locked row. Small, mechanical,
and it is a prerequisite for taking any CSF number seriously.

---

## 5. W1 — make the drop countable, in every service

The generalised Finding 3. It comes before the resolver rewrite because it is the
instrument that measures whether the rewrite worked, and the last two attempts were
both declared done on a green suite.

Per service, in the run-AI response **and** the audit row:

- `suggestions_received`
- `suggestions_applied`
- `suggestions_dropped[]` — itemised, with a `reason` and the offending key
  **verbatim as the model wrote it**

Verbatim is the point. `{"reason": "unknown_key", "key": "GV.OC-1"}` tells you
instantly that the catalogue holds `GV.OC-01`. A bare count tells you nothing.

**Per-reason from day one is not optional.** `zt.py:495` folds three distinct
outcomes into one `continue` — unknown code, `row.locked`, and `code in protected` —
and `protected` covers every client-answered row on a fixture run
(`provenance.py:42-45` records a tenant with 5 of 37 answered). A single number there
is _normal by-design operation_ rendered as an alarm, which is exactly the warning
issue #31 rejected as "would fire constantly and be trained away". `unknown_key` and
`out_of_range` must render separately from `locked` and `protected`.

**Finding 11 lands here, not later.** A surfaced counter that is wrong is worse than
an absent one. For ATT&CK that means fixing the fold-asymmetry
(`_fold(name) != cited.strip().casefold()`) **before** the number is ever rendered.

**Order — corrected.** The first draft said "Risk first, it is UI-only, the cheapest
proof". That is false: the counters are computed at generate time and **never
persisted**. `_serialize` defaults both to `0` (`risk.py:553-559`), so
`GET /register/latest` (`:550`) and `POST /register/export` (`:530`) both return
zeros, and `RiskRegisterDashboard.tsx:210` overwrites the panel state with the export
response. Ship W1 for Risk as described and a register missing three batches will
read **"0 batches failed"** the moment anyone clicks Export — an invisible drop
converted into a visibly asserted zero. Risk needs a migration on `RiskRegister`
first, so it is the most expensive step, not the cheapest.

Revised order: **CSF → ZT → Risk (with its migration) → ATT&CK [#29]**. Fold F6 and
F10 into the Risk step.

**A caveat W1 must state rather than discover later.** Fixture mode cannot exercise
these counters at all: the fixtures echo the payload keys back verbatim
(`fixtures.py:102-105`, `:147`, `:178-182`, `:316-332`), so catalogue-miss drops are
structurally zero in CI. The counters can only be validated by synthetic unit tests,
and §2's "measure the near-miss rate from real runs" has **no CI path** — it needs
live runs on real client data, which nothing currently budgets for. F6 is the
concrete case where the fixture is actively masking a live defect.

**Test invariant.** For each service: a run whose suggestions all miss the catalogue
must (a) change zero rows, (b) report a non-zero drop count _by reason_, (c) surface
it. Today (a) alone holds, and (a) alone is indistinguishable from success.

---

## 6. W2 — ATT&CK resolver rewrite + tri-state

Unchanged from `docs/plans/2026-08-08-attack-citation-resolver.md` Parts 5 / 5.1.
Two constraints this plan adds:

1. **It stays ATT&CK-only** (§2).
2. **Narrow-confirmed cannot ship against a mutable approved list — and W3 as
   originally scoped does not make it immutable.** See W3. Either W3 widens, or
   "confirmed" must mean _present in the list at the moment of approval_, which
   requires an approval-time snapshot the schema does not store. **Pick one
   explicitly; do not assume the dependency is discharged.**

Note for reproduction: on `main`, `_client_tool_names` (`attack.py:472-486`) excludes
only DISCARDED and its docstring says so (`:464-470` — _"DRAFT still counts"_). The
approved-only allow-list is **[#29]**, so "the approved list is mutable" only bites
once #29 lands.

---

## 7. W3 — Tech Debt: make approval mean something

Tech Debt-only for the _list_ mutability (CSF's separate hole is W0; ZT is clean).

**There are five doors into an APPROVED list, not three.** The first draft listed
three and mis-attributed one:

| Door                                       | `file:line`                                                               | Effect                                           |
| ------------------------------------------ | ------------------------------------------------------------------------- | ------------------------------------------------ |
| `_editable_list_or_404`                    | `tech_debt.py:344-355`                                                    | blocks RELEASED (route-dead) + DISCARDED only    |
| add-components                             | `tech_debt.py:609-620`, adds at `:635-652`                                | adds `CapabilityItem` rows                       |
| `patch_capability_item`                    | `tech_debt.py:671`, guard `:696-707`                                      | edits any field including `name`                 |
| `include_excluded_row`                     | `tech_debt.py:383-410`                                                    | appends an item, `confidence_pct=None` at `:403` |
| confirm / override security classification | `tech_debt.py:504-517`, `:550-554` via `_editable_item_or_404` `:467-478` | **changes allow-list membership**                |

**The first draft's recommendation — re-approval on the ADD path only — does not
close the finding.** Two reasons, both confirmed:

- `patch_capability_item` can change `name`, and the ATT&CK allow-list is
  `frozenset(t.lower() for t in tools)` built from those names (`attack.py:545`). It
  can also change `annual_cost_usd`, and `clients.py:760-779` reads `CapabilityItem`
  rows **live** for the client Tech Debt dashboard — it is not a snapshot. So an edit
  after release changes the client's dashboard total while the released PDF says
  otherwise. **That is N-010's exact failure mode arriving by a different route**,
  and the carve-out leaves it open.
- The confirm queue is a _sanctioned_ post-approval mutation of allow-list
  membership: `security_class_confirmed = True` removes the row from
  `security_scope_filter()` (`security_scope.py:45-51`), whose own docstring
  (`:9-11`) says _"Drop a real security tool from it and the model cannot name it, so
  the technique it covers reads as uncovered. That is a fabricated gap."_ Confirm a
  tool non-security after an ATT&CK run and its "confirmed" citations are confirmed
  against a list that no longer contains the tool.

So the honest choice is between (a) an approval-time membership snapshot, which W2
needs anyway, and (b) confronting the confirm queue instead of exempting it. **The
snapshot is the cheaper and more honest option** — it makes "confirmed" mean what it
says without breaking a workflow that exists by design.

**Sharper than issue #32 records:** `include_excluded_row` writes
`confidence_pct=None` (`tech_debt.py:403`), which is the _same value the human-
curation path writes_ (`:722`). `EditableCapabilityTable.tsx:91` returns `"success"`
and `:107` returns `"Human-curated"` for `pct === null`. So a row nobody reviewed
renders a **green pill reading "Human-curated"** — an affirmative false claim, not
merely a missing signal.

**Correct the docstring either way.** (Note: `_client_capability_rows`, whose
docstring issue #32 quotes, is **[#29]** and does not exist on `main`.)

---

## 8. W4 — the RELEASED status decision (premise corrected, recommendation reversed)

**The first draft asserted "`XStatus.RELEASED` is never assigned anywhere in the
codebase." That is false**, and the error was a grep scoped to `apps/api/app`
presented as a repo-wide claim. It is assigned eight times:

```
apps/api/scripts/seed_demo.py:480/570/674/781   ServiceStatus.RELEASED
apps/api/scripts/seed_demo.py:492               CapabilityListStatus.RELEASED
apps/api/scripts/seed_demo.py:583               CsfAssessmentStatus.RELEASED
apps/api/scripts/seed_demo.py:688               ZtAssessmentStatus.RELEASED
apps/api/scripts/seed_demo.py:794               AttackAssessmentStatus.RELEASED
```

The correct claim is narrower and different in kind: **no API route transition ever
assigns RELEASED; the only writer is the seed script.** That matters enormously,
because the e2e suite runs against seeded data, so the guards **do** fire there —
`e2e/smoke/s5-attack.spec.ts:18`, `s6-zt.spec.ts:18`, `s7-csf-playbook.spec.ts:14,85`,
`s4-techdebt.spec.ts:100`, and CLAUDE.md's own `s34` note (_"the seeded service was
released, so the button was disabled"_).

**Therefore the first draft's recommendation is reversed.** Option B — delete the
comparisons, key on `Deliverable.released_at` — would un-lock the seeded Atlas
capability list (`seed_demo.py:489`), which has no released `Deliverable` behind it.
`clients.py:760-779` then serves a demo client dashboard that can be edited under a
released PDF, and four e2e specs flip from asserting read-only to silently exercising
a path they were written to prove was blocked — the `s34` lesson, repeated.

The read side is also larger than the first draft's table. Two modules compare the
**raw string** and are invisible to an enum grep:

- `services/stages.py:180-181` — `released = status == "released"`
- `routes/service_stages.py:54` — `_CLIENT_SUBMITTED = frozenset({"submitted","approved","released"})`

Consequence, confirmed: a service released through the API (which sets
`Deliverable.released_at` and no status) still computes `released = False`, so
**the progress bar shows `release` as the current incomplete stage on a service whose
report is already with the client.** `test_service_stages.py:277-281` constructs
`status="released"` directly — a test proving a state no route can reach. Option A
fixes this; Option B does not, and the first draft never priced it in.

And three comparisons are **fail-closed denies**, not idempotence guards:
`attack.py:346`, `csf.py:466`, `zt.py:660` — all
`if user.role != ADMIN and a.status != RELEASED: 403`. Deleting rather than
repointing these **grants client-role users unreleased assessments**. They are pinned
by `test_attack_routes.py:385`, `test_csf_routes.py:330`, `test_zt_routes.py:435`, so
a straight delete goes red — but the first draft's instruction to "remove or repoint"
invited the wrong edit.

**Revised recommendation: Option A** — assign `RELEASED` to the parent record inside
the release path — with the blast radius handled deliberately rather than assumed
away: it makes the seeded and API-created worlds agree, fixes the stage bar, makes
Tech Debt's mutability lock live, and leaves the fail-closed denies working
unchanged. It is the larger change; it is also the one that does not quietly remove
protection that currently fires.

**This supersedes D-035 §1**, which recorded the deferral verbatim
(`DECISIONS.md:888-898`): _"Flipping the assessment to RELEASED on release remains a
possible future consistency cleanup — out of scope here."_ The W4 PR must supersede
that decision explicitly, not silently contradict it.

---

## 9. W5–W8

### W5 — Reopen ×4 + shared release-staleness guard (ATT&CK plan Part 3)

Independently re-verified on `main` and it holds:

- `release_deliverable()` (`deliverable_release.py:40-116`) performs **no staleness
  check** — tenant (`:60`), kind (`:62`), `finalized_at` (`:68`), `released_at`
  idempotence (`:77`), write (`:89`). Nothing else.
- `documents_stale` exists on ATT&CK (`attack_assessment.py:61`), CSF
  (`csf_assessment.py:76`), ZT (`zt_assessment.py:73`), **not** on `CapabilityList`.
- **CSF clears it in two places** — `csf.py:1920` (finalize) and `csf.py:1694`
  (**playbook export**) — where ATT&CK and ZT clear it in one. Resolve before writing
  the guard: a playbook export clears staleness without generating a `Deliverable`,
  so the guard will pass on a genuinely stale CSF deliverable and CSF alone will have
  a hole the tests will not show.
- **`documents_stale` is set only by the three run-AI paths** (`attack.py:813`,
  `csf.py:1532`, `zt.py:539`). No manual edit sets it — including W0's
  `patch_dimension_score`. So invariant 6 must be tested through a **manual-edit**
  path, not only an AI re-run, or it proves nothing.

Part 3 §3.5's Tech Debt decision still needs making, and now interacts with W3: an
approval-time snapshot is most of the machinery a `CapabilityList.documents_stale`
would need.

### W6 — Risk Register: export _is_ release

Verified:

- `POST /risk/clients/{cid}/register/export` (`risk.py:451-530`) has **no approval
  gate** — no approved state exists on a register.
- Export sets `reg.finalized_at = utcnow()` (`risk.py:520`).
- `clients.py:886` gates the client dashboard on exactly that, and `clients.py:927`
  reports it to the client as `released_at=reg.finalized_at`.

The other four services have a deliberate review window between finalize and release
(`s40` tests it). Risk has none — an admin clicking Export to _look_ publishes. And
the register is generated straight from batched AI synthesis (`risk.py:349`) with
F5/F6/F7/F10 all dropping silently, so the least-reviewed output of the five is the
one with no review window.

**Recommendation: split export from publish.** Costs the first draft understated:

- `e2e/smoke/s30-risk-dashboard.spec.ts:60-74` POSTs export with the comment
  `"export (finalize) register"` and then asserts the client dashboard renders. It
  fails until it also calls the new publish action.
- `DECISIONS.md:940` records the current model as a decision; W6 reverses it and must
  amend `DECISIONS.md` in the same PR (CLAUDE.md requires it).
- `seed_demo.py:1117` sets `register.finalized_at` directly; the seed needs the new
  publish marker or the demo tenant loses its Risk dashboard.

**Fix in the same change — a new generate un-publishes the released register.**
`clients.py:880-885` selects the highest-version register unconditionally, then `:886`
requires `finalized_at`. `finalized_at` is per-version and only export sets it. So
clicking Generate for v2 makes the client's dashboard 404 immediately while they are
reading it. CSF is explicitly tested the other way for this exact case
(`test_value_summary.py:444-488` — _"Once v1 is released, a NEW v2 DRAFT … still the
released v1's 5 gaps"_). W6 widens the unpublished window, so it makes this worse
unless fixed together.

**Minor, SUSPECTED:** all five stamp generated deliverables
`origin=ArtifactOrigin.CONSULTANT_APPROVED`. For ATT&CK/ZT/Tech Debt finalize is
gated on APPROVED so the label is true. **Two producers make it false:** Risk
(no approval exists) and **CSF's `export_playbook`** (`csf.py:1554-1577` — tenant,
`a is None`, and `if not all_rows`; **no status gate**), which writes six artifacts
through the shared `_write_artifact` (`csf.py:1673`, origin at `:1758`) from a DRAFT
assessment. `AUTOMATED_DRAFT` exists as the accurate alternative. Check the enum's
consumers before treating it as a defect — it may be intended as "consultant-side
generated".

### W7 — Watermarking (ATT&CK plan Part 2 §2.2)

The grep claim re-verified: no `render_pdf` / `render_xlsx` / `render_docx` caller
outside the five route modules (plus `seed_demo.py` and the exporter unit tests).

But the ATT&CK plan frames watermarking as needed _when_ draft previews relax the
gate. **Two services already produce unapproved documents today** — Risk (no approval
model) and CSF playbook export (no status gate). Those two need the watermark now,
before any preview relaxation, not as part of it.

### W8 — Adversarial audit in CI

The mechanism is the deliverable: a local hook binds whoever installed it, CI binds
everyone.

**Blocker first.** `.claude/agents/adversarial-reviewer.md` is committed on `2bbb00a`
(PR #29's branch) and is **not on `main`** — `.claude/agents/` does not exist in this
tree. It is therefore not a registered `subagent_type` in a session started from
`main`, and it was not one for this plan's audit (both passes ran with its definition
inlined into a general-purpose agent, which works but is not the committed contract).
**Land the agent file on `main` as its own small PR before anything depends on it.**

---

## 10. What the adversarial audit changed

Recorded so the gate in §12 reads as a practice rather than a slogan.

| Draft claim                                            | Audit verdict                                                                                                                     | Now                                                       |
| ------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- |
| "`RELEASED` never assigned anywhere"                   | **FALSIFIED** — 8 assignments in `seed_demo.py`; e2e depends on the guards firing                                                 | §8 premise restated; **recommendation reversed A over B** |
| "CSF and ZT genuinely lock on APPROVED"                | **FALSIFIED** for CSF — 3 unguarded routes incl. the score table, no audit row                                                    | promoted to **W0, first workstream**                      |
| "Risk first for W1 — UI-only, cheapest"                | **FALSIFIED** — counters unpersisted, `_serialize` returns 0, export overwrites the panel with a false zero                       | Risk moved last, needs a migration                        |
| "W3: re-approval on the ADD path only"                 | **FALSIFIED** — edit path changes `name` and cost, read live by the client dashboard; confirm queue mutates allow-list membership | replaced with the approval-time snapshot                  |
| "Risk is exempt from the tri-state (closed catalogue)" | **PARTLY FALSIFIED** — F6 is prompt/parser drift, fixture-masked                                                                  | pulled into W1                                            |
| "F9 — confirm before fixing"                           | **UNDERSTATED** — live on `main`, re-arms the 0035 incident                                                                       | promoted above most of W1                                 |
| Three doors into an APPROVED list                      | **INCOMPLETE** — five, one mis-attributed                                                                                         | corrected                                                 |
| §4 table complete                                      | **INCOMPLETE** — missed `stages.py` raw-string compares and three fail-closed 403s                                                | added                                                     |
| F7 is Risk-only                                        | **INCOMPLETE** — ATT&CK has the same unread counter                                                                               | corrected                                                 |
| Every reference verified on `main`                     | **PARTLY FALSE** — `_client_capability_rows` is #29-only                                                                          | **[#29]** markers added throughout                        |

Two claims were attacked hard and **held**: the closed-catalogue argument for CSF/ZT
key matching (§2), and every W5 claim about `release_deliverable` and
`documents_stale` topology.

---

## 11. Ordering

```
W0 CSF approved-assessment write guard      ← first; smallest, most severe
  ├─ W1 drop counters: CSF → ZT → Risk(+migration, F6, F10) → ATT&CK [#29]
  │    └─ W2 resolver rewrite + tri-state (ATT&CK)     ← gated on W3
  ├─ F9 ZT provenance fix                    ← independent, land early, live defect
  ├─ W3 Tech Debt approval-time snapshot
  │    └─ (unblocks W2's narrow-confirmed)
  ├─ W4 RELEASED status decision (Option A, supersedes D-035)
  │    └─ W5 reopen ×4 + shared release-staleness guard (+ CSF double-clear)
  │         └─ W7 watermarking + freeze-on-generate
  └─ W6 Risk export/publish split (+ the v2-un-publishes defect, s30, DECISIONS, seed)
W8 land the agent file on main now; the CI job can follow
```

Hard constraints:

1. **W1 before W2** — without counters there is no way to tell whether the rewrite
   improved anything, and the last two attempts were both declared done on green.
2. **W3 before W2** — narrow-confirmed is unsound against a mutable approved list,
   **and the snapshot is the thing that discharges it**, not the ADD-path carve-out.
3. **W4 before W5** — the reopen guard is the guard-keyed-on-a-dead-status shape;
   settling the status question first is what stops it recurring.
4. **W0 before anything CSF** — there is no point counting drops into a table any
   admin can overwrite silently after release.

## 12. Invariants to test (beyond the ATT&CK plan's four)

1. Each of the five: a run whose suggestions all miss the catalogue reports a
   non-zero drop count **by reason** — not merely zero changes.
2. `suggestions_received == suggestions_applied + Σ(dropped by reason)`. No
   suggestion falls between states.
3. A ZT capability whose suggested stages were both rejected does **not** have
   `answer_source` rewritten to `ai` (F9) — asserted on a **live-mode** run, since
   `protected_keys` is empty there.
4. A Risk entry whose likelihood/impact failed to parse is visibly untiered, and
   `total_entries` reconciles with the tier bars (F6).
5. Risk's technique allow-list with an empty ATT&CK assessment does not silently
   become the whole MITRE catalogue (F10).
6. `PATCH /csf/dimension-scores/{id}` returns 409 on an APPROVED assessment and
   writes an audit row on a DRAFT one (W0).
7. A capability item recovered via `include_excluded_row` is distinguishable from a
   human-curated one in both the API response and the pill (W3).
8. `release_deliverable` refuses a stale parent in all four services — tested through
   a **manual edit**, not an AI re-run, and including the CSF playbook-export path
   that clears the flag (W5).
9. A newly generated Risk register v2 does not remove the client's access to the
   published v1 (W6).

## 13. Explicitly out of scope

- A CSF/ZT/Risk code-format normaliser (§2 — measure first, and note W1's caveat that
  CI cannot measure it).
- Extending the tri-state beyond ATT&CK.
- Anything on PR #29 beyond what its own plan lists.

## 14. Gate

Every workstream merges on a clean adversarial-reviewer audit, not on a green suite.
§10 is the argument: this plan's own first draft was internally consistent,
evidence-cited, and wrong in four load-bearing places — including one recommendation
that would have un-locked seeded demo data and one service-wide "this is fine" over a
released-assessment write hole. The suite was green throughout.
