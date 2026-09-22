# Project Context — state of `main`

_Last updated: 2026-09-21 (status correction, `main` at `8e68d46`: the `DELIVERY_PLAN.md` MVP path was stale across items 6, 7, 8, 9, 11 and 12 — item 9 included, because its "Remaining from the original seven" line named #115, #46 and #109, every one of which had landed. Items 7, 11 and 12 are complete; item 8's #123 half shipped and the export/publish half it is NAMED after has shipped nothing and owns no issue; item 6 has F10 left, which owns no issue; item 9 has #185 and #194, neither with a live client-facing defect. Those rows — and only those — now cite landed code rather than issue state: rows 0 through 5a, 9a and 10 still rest on a PR number and a merge date, which is said here because a sentence quantifying over the table would tell the next reader the check has been done everywhere. NOT done here and flagged for Gene: the 12–18 headline and the estimate table are stale and unchanged; the live `mvp-blocking` blockers own no item; F10 needs filing; and #185's label should move to `post-mvp` to match the row. Earlier 2026-09-09: #237 shipped in PR #242 — Risk synthesis now reads only APPROVED/RELEASED assessments, so DRAFT work can no longer be exported under a client's name; the generic `_latest` is split three ways -- `_exists_for_gate`, `_finalized_for_synthesis`, and `_latest_register` for the register row, D-075, `main` at `851348b`. Landing with THIS PR, not yet on `main` when it was written: #114 fixed — all four client dashboards and the four value-loop cards now resolve their assessment from the released deliverable's `parent_version` rather than from "latest APPROVED", so the numbers and the version label beside them name the same record; `_latest_finalized` is deleted, D-073; earlier 2026-09-07: the next 15.5.24 RCE patch, and the exposure correction that goes with it — see the dated section below; earlier 2026-09-06: #131 fixed — the approved snapshot's vendor and spelling now win the capability merge, D-064, and item 7's `mvp-blocking` line below is updated for it; earlier the same day: `DELIVERY_PLAN.md` reconciliation recorded, the item table reconciled against what shipped, the #183–#196 issues each given a disposition, and the item 7 and item 9 sizing sections re-derived. The rest of the `mvp-blocking` mapping below was NOT revised and predates `f10955c` — see #201; earlier 2026-08-30: the plan correction: `mvp-blocking` defined, items 11 and 12 added, item 8 split; earlier 2026-08-26: item 10 / PR #155 merged, `main` at `fbca899`; earlier 2026-08-24: #130, the redaction over-match; earlier: cross-service integrity; PRs #34, #35, #36, #39, #42,
#45, #48, #54, #56, #58, #63, #66, #78, #80, #81, #82 merged, `main` at `a7db134`,
CI green). NOTE: this
repo (`gene-png/080426SHIELD`) starts from a single baseline-import commit on
`main` carrying the working tree through `v3.7.0`; the PR numbers cited in the
sprint history below belong to the upstream repo, not to this one. This file
describes the
project as of the branch it sits on and is updated ONLY as part of a PR. Durable
facts and environment gotchas live in `CLAUDE.md`; personal in-flight status
lives in `context/<name>.md`; per-sprint detail lives in `SPRINT_<n>.md`._

## Current state

**#347 landed as tier-1: `CLAUDE.md` was being truncated before any agent read
it.** At 210,958 bytes against a 150,000-byte reader limit, the last 29% was cut
silently — and the cut landed on the merge rule. `An agent merges on green` sat
at byte 192,494, so agents read that a PR "tripping condition 5" comes back to
the human and could not read which paths trip it. All four occurrences each of
`apps/api/tests/**` and `tests/gates/**` were past the boundary.

Three things changed. The **merge rule moved to the top** of `CLAUDE.md` (now
bytes 6,437–14,800), because position is part of a rule when truncation cuts
from the end. The file was **trimmed 210,958 → 148,814 bytes** by moving
incident narrative to D-079 and keeping the instruction; no rule was deleted.
And **`apps/api/scripts/check_claude_md_size.py`** now refuses the file above
150,000 bytes, wired as the CI step "governance file fits in a reader".

**It was misdiagnosed as #170** (injected-context lag) because truncation and
staleness look identical to the reader. #170 is not closed — it may still be
real — but the `tn-gates` report is withdrawn from it.

**Measured window, which corrects the estimate:** condition 5's test glob
crossed the cut on **2026-09-10** (`f7c7c6ed`), not 2026-09-19, and
`tests/gates/**` was born past it on 2026-09-21. Of **70** PR merges in that
window, **51 tripped condition 5 only through a path past the cut**; 49 of those
carried no migration, and 20 edited the gate harness itself. That establishes
the control was unavailable, not that any PR merged wrongly — whether an agent
merged unattended is not recorded anywhere git can answer.

**Residual: 1,186 bytes of headroom.** The next substantive addition to
`CLAUDE.md` is paid for by a trim. `DECISIONS.md` (293,879 bytes) is
deliberately not gated — it is the RECORD, grepped by D-number, not injected
into every agent's context. `DELIVERY_PLAN.md` at 140,438 bytes is the next file
to cross.

**#336 landed: a gate now enforces that disclosures reach a reader.**
`apps/api/scripts/check_disclosure_consumers.py`, wired as the CI step
"disclosures reach a reader". A field on a `*Response` model recording what was
withheld, dropped or rejected must have its name referenced under
`apps/web/src` OR in an exporter -- "a screen or a delivered artifact", per the
definition-of-done rule.

**18 such fields today: 15 reach a reader, 3 do not and are exempt with a
tracked reason.** An earlier draft of this line said "all reachable", which was
false on both halves -- it stated a count as a clean bill of health over a set
the gate's own exemption text calls "a REAL unconsumed disclosure". The gate
prints the split on every clean run, so the number here is a summary of a
measurement rather than a claim of its own:

    check-disclosure-consumers: 15 of 18 disclosure fields reach a screen or a
    deliverable; 3 do NOT and are exempt with a tracked reason

**Every exemption has an expiry, and two of the three expire on a PR that is
already open.** `batches_total` and `batches_failed` are unconsumed only because
the banner that renders them is in #376; the moment it lands they are ordinary
reachable fields and their entries must go. `unusable_target_codes` is the third
and is a live client-facing defect rather than a timing artifact -- it reaches no
screen at all, and it is **#387**.

That matters more than the count. The gate was passing over
`unusable_target_codes` before this branch, because per-service scoping did not
separate two models of the same service: `zt/exporters.py` carries the token
`zt` and reads a DIFFERENT model's field on a different route. A gate green over
a live instance of the defect it exists to catch.

Two design calls worth knowing. The consumer surface is TWO surfaces, not the
web alone: `unusable_target_codes` reaches the client only through
`zt/exporters.py`, so a web-only search would have reported a defect over a
field that already reaches the reader who matters most. And the audit `details`
payload -- #322's population, which are dict keys rather than schema fields --
is checked STRUCTURALLY, by asserting a generic renderer exists, because
enumerating its keys would report violations over a payload that a generic
renderer makes fully visible. That arm is exempt until #351 lands, with an
expiry stated in the code.


### `mvp-blocking` issues — the live list is a command, the mapping below is history

**The count is not written here. Run it:**

    gh issue list --label mvp-blocking --state open --json number --jq length

**A command instead of a number, and this is the endpoint of rule 1 rather than
a new idea.** The heading used to say `14` under a paragraph certifying it
freshly read. Both were true on 2026-08-26 and false within days. Replacing that
with a `<!-- counted: … -->` marker only moves the problem: a marker is a
FRESHNESS CLAIM, and on 2026-08-30 one certified `17` that a re-label in the
same session made `16` — while the PR that closes `#165` sat green, about to
make it `15`. A claim can go stale. A command cannot, and anyone who wants the
number runs it.

**What stays is the MAPPING**, because an issue's owning item does not change
when a different issue closes. Durable half keeps, volatile half goes. Every
blocker belongs to an item in `DELIVERY_PLAN.md` — a property this list did NOT
have on 2026-08-26, when four were orphaned. By item:

- **7** — `#178` ·
  **9** — `#114 #115 #46 #109 #124 #125 #126` ·
  **6** — `#121 #122 #132` · **8** — `#123`
- **11 (new)** — `#152 #153`, the redaction leaks item 10 filed rather than
  fixed and then orphaned when it closed
- **12 (new)** — `#168`, the pre-commit hook set running three tools at versions
  no gate uses

**#165 and #168** have since closed — naming them rather than saying "both of
those", whose nearest antecedent is the item-11 and item-12 bullets directly
above. **(Item 11 has since closed too — #152 and #153 landed 2026-09-10 in PR #279, `52568a3`; this sentence said "item 11 is still open" until 2026-09-21.)** The mapping above is kept rather than
pruned because that is what this list is for: `#165` and `#168` are CLOSED
(the prettier-pin PR #311, merged 2026-09-11, which took item 12 with it), and
`#159` has lost the label as planned — it is developer tooling and does not
meet "the MVP cannot ship while this is open", the definition now written into
`DELIVERY_PLAN.md`. `#159` itself is still open, correctly and off the board.

Run the command above for what is open now; an issue's owning ITEM is the
durable half and does not change when the issue closes.

**EVERY ISSUE IN THE MAPPING ABOVE IS NOW CLOSED. Measured 2026-09-21 at
`8e68d46`** (`gh issue view <n> --json state` per issue; landed code verified
for each and cited in the `DELIVERY_PLAN.md` row that owns it). The mapping is
kept because it is the durable half, but it is no longer a to-do list and was
read as one: a night's work order was written on 2026-09-21 from the
`DELIVERY_PLAN.md` rows this mapping mirrors, and pointed at work that had
already landed.

**The heading is not what misled anyone, and an earlier draft of this paragraph
said it was.** It blamed "a heading that says \"Open\"" — but the heading four
lines above already says the opposite, and no heading in this file contains the
word. A sentence the file itself falsifies, misattributing the incident to the
one thing that had been fixed. The actual vector is named above: the plan's
ROWS, not this mapping and not its heading.

**So the section's rule has a hole this exposes rather than fixes.** Replacing
the count with a command made the COUNT honest and left the MAPPING to go stale
by a different route — not by drifting, but by every member of it closing while
the live blockers appear nowhere here and own no item in `DELIVERY_PLAN.md`.
Run the command and compare what it returns against the mapping; where a
returned number is absent from it, that blocker has no owning item, which
`DELIVERY_PLAN.md` states is the condition under which its total silently stops
covering its own definition of done. At `8e68d46` the only returned issue
carrying `unowned-with-reason` was `#220`. Assigning the rest is a scoping
judgement, flagged for Gene rather than guessed here.

**#185 and #194 are open and neither has a live client-facing defect.** #185's
headline defect — the swallowed fetch failure — was fixed by `3933c46` across
all four workspaces; what survives is the `Promise.all` coupling in
`csf/CsfWorkspace.tsx` and `zt/ZtWorkspace.tsx` and a generic message in place
of the typed reason, both admin-surface and both disclosed. #194's duplication
is real and current but all three sites agree, so nothing renders wrongly.
**#194 has since CLOSED** (PR #398, `1281cbd`, `lib/assessment-targets.ts`),
and its successor **#406** — the intake option lists, which expressed the same
floor by OMISSION, plus four Pydantic bounds on the API side — is on
`fix/406-target-floor-derivation`, PR #427, unmerged. That branch derives both
option lists from the constants and replaces the bounds with a typed
`{reason, message}` refusal in `_validate_targets`, so a client who picks an
impossible target is told which control to change instead of reading "Failed
to submit intake." **#85 is the half it deliberately leaves open**: the two
self-assessment submit routes write the same columns and still accept a
target of 1, `routes/csf.py` with no range check at all.
**The row now judges #185 out of item 9's completion bar, so its `mvp-blocking`
label should move to `post-mvp`** — the row and the label must agree, and the
row is what moved. The reasoning is in the `DELIVERY_PLAN.md` item 9 row so the
call can be overturned rather than inherited.

**Items 6 and 8 are NOT complete though every issue in the mapping closed**, for
the same reason both times — an item's issues are a sample of its scope, not its
definition. Item 6 still carries F10 (the allow-list swap the 2026-08-08 plan
folds into it by name, live in `routes/risk.py`, no issue filed). Item 8's
export/publish split, what the item is named after, has shipped nothing and owns
no issue at all, so issue state reads complete over it. Both are written up in
the `DELIVERY_PLAN.md` rows with the quoted code.

`#125` and `#126` closed with Track C's first PR (`#197`, merged 2026-09-05).
**`#124` deliberately did NOT ship with them**, which departed from the "must
land together" instruction in `DELIVERY_PLAN.md`; the deviation and its reason
are recorded there beside that instruction, in `#143`'s form. The short
version: the `#125` engine fix, landed alone, introduced a silent
client-visible regression that a full green backend suite could not see, and a
branch shown to do that is one to narrow rather than widen.

**`#124` then shipped on its own branch, `fix/zt-dashboard-engagement-target`,
as the immediate next one** — so the deviation's stated cost is paid rather
than outstanding. The ZT client dashboard now resolves the engagement target
through `resolve_target_stage` and carries `target_stage_source`, and the
per-capability rule `analyze_gaps` applies is extracted so the dashboard and
the deliverable cannot disagree about a target. What the review found in the new
code is filed rather than fixed there: `#209` (a released dashboard recomputes
against a target that stays writable after release), `#208` (the ZT bar axis
prints CISA's four stage labels under a DoD engagement) and `#207` (the
value-summary card reports ZT and CSF gap totals without saying which target
they were computed against).

That PR also carries fixes the review found rather than the issues named —
notably that the Tech Debt exporter still called a floor a "Total" while the new
client dashboard called the same list "partial". Two surfaces, one list,
contradictory claims, and the document is the half the client keeps.

Not labelled `mvp-blocking`, and deliberately so — recorded because unlabelled
and out-of-scope look identical otherwise: **#151** (Tailwind classes naming
undefined design tokens render as nothing, 18 occurrences), **#154** (the
computed glue-alphabet sweep, filed with its reasoning and measured as searching
an empty space), **#156** (ruff isort classifying `apps/api/scripts` by whether
an unrelated top-level `scripts/` exists), **#143** (the pre-push hook's
fail-open).

### 2026-09-08 — the client dashboards labelled one record's numbers with another's (#114, D-073)

Four client dashboards (ATT&CK, ZT, CSF, Tech Debt) and the four value-loop
cards behind `/value-summary` resolved their assessment with `_latest_finalized`
— highest-version row whose status is APPROVED or RELEASED — while reporting
`deliverable_version` and `released_at` from the released **deliverable**. Two
independent lookups, rendered as one claim.

The helper's docstring asserted this kept the client "pinned to released work".
It did, until a consultant clicked Approve on v2 — the mandatory step before v2
can be finalized. From that moment the client's dashboard showed v2's numbers
under a header naming the v1 report they had downloaded, with nothing marking it
a preview.

All eight call sites now resolve through `Deliverable.parent_version`, which is
stamped at finalize and is the only record of which assessment a report was built
from. `_latest_finalized` is **deleted** rather than narrowed: no status filter
can answer the question, because the answer does not live in the assessment
table. A NULL or unresolvable link refuses with a typed 404
(`dashboard_version_unresolved`) and a WARNING naming which of the two causes
fired — never a fallback to "latest", which would reinstate the defect for
exactly the services most likely to hold several versions.

Measured before and after against the real route responses, per surface:
ATT&CK 20 covered → 5; CSF 100% → 50%; ZT 100% → 50%; Tech Debt $708,000 of
identified savings → $38,000; the executive card 9 gaps → 5. Every one of those
was rendered under `deliverable_version: 1`.

**`risk_dashboard`'s READ is correct** — it takes `version` and `entries` from
the same `RiskRegister` row, so it has no pairing to break. The register's
SOURCE selection is a different question and was not in this sweep. As this
branch was written, `routes/risk.py::_latest` picked the newest assessment
excluding only DISCARDED, so a DRAFT could be synthesized into a register that
is exported to the client. That was filed as #237 and has since shipped: PR
#242 landed on `main` at `851348b` and closed it (`gh issue view 237` ->
CLOSED/COMPLETED, 2026-09-09), splitting the helper THREE ways -- and recorded
as D-075. Verified by reading `risk.py` at `851348b`, not from the PR title:
`_exists_for_gate` answers the gate (its three call sites are the ATT&CK, CSF
and ZT existence checks), `_finalized_for_synthesis` applies the
APPROVED/RELEASED filter, and `_latest_register` fetches the register row --
which is NOT the gate. **There is no `_latest` in `routes/risk.py` any more**, so the symbol
this paragraph used to name will not resolve. **A SECOND residual sits in `routes/clients.py` itself** —
`risk_dashboard` takes the highest-`version` register with no finalized filter,
so generating v2 hides a finalized v1 the client already has. Tracked in #123,
which queues behind this PR on the same file. **FIXED 2026-09-10 in PR #272
(`6199c79`); recorded here 2026-09-21.** `risk_dashboard` now selects under
`RiskRegister.finalized_at.is_not(None)`. The paragraph stands as the record of
the residual this track filed rather than fixed, but the present-tense
description above had become a live false claim about the code — someone acting
on it would have rebuilt what already ships.

Two consequences of the refusal are filed rather than fixed, both outside this
track's territory: the dashboard pages key their error copy on HTTP status
rather than `reason`, so the refusal reads as "not released yet"; and
`/value-summary` USED TO RAISE, which took down the whole client home page —
overturned 2026-09-09, so the slot now nulls with a stated reason and `#236` is
not reachable from this endpoint. **The superseded behaviour is described in
the rest of THIS sentence, not in the paragraph below** — which is the live
"#59 stays deferred" decision and is not superseded by anything: it raised, and
`/home` fetches it in an unguarded `Promise.all` with no error boundary
(#236). The refusal's log
names two of three possible causes (#238).

**#59 stays deferred**, as `DELIVERY_PLAN.md` decided before the work started.
Every `Deliverable` the product builds (four finalize routes) and the one
`seed_demo.py` builds stamp `parent_version`, so the refusal is unreachable
except on rows finalized before migration 0041. If it ever fires it has named a
genuinely un-repairable legacy row, which is when #59 stops being deferrable.

### 2026-09-07 — the next RCE patch, and what the exposure actually was

`next` 15.5.23 to 15.5.24 shipped in PR #225, covering `GHSA-p293-qw3h-jr36` and
`GHSA-2xp9-vwfh-vxw4`. **The patch was correct to ship. The exposure language
around it was not, and the corrected version is the one to carry.**

For seven days this was described as "two unauthenticated RCEs open". Measured:

- `GHSA-p293-qw3h-jr36` is **windows-hosted servers only**. Production runs Linux
  containers. It was live on a Windows dev host, not in production.
- `GHSA-2xp9-vwfh-vxw4` needs the **Image Optimization API**. No application code
  calls it — 0 `next/image` imports, 0 `avif` references — but **that is not what
  decides whether the route exists.** An earlier draft of this section cited "no
  `images` block in `next.config.mjs`" as evidence the optimizer was not in play.
  That is exactly backwards: the absence of that block is the state in which the
  route WAS mounted, because `/_next/image` is mounted by the framework regardless
  of what imports it.

  **Measured against the standalone artifact** — the production build shape, not the
  dev server: `/_next/image` answers **400 without** `images: { unoptimized: true }`
  and **404 with** it, while a genuinely absent route answers 404 either way. 400 is
  a mounted handler rejecting the request; 404 is no handler at all. So the route
  was reachable and answering for as long as that line was absent, and the config
  file's silence was the thing being read as its absence. PR #230 adds the line and
  a CI step holds it there.

  Reachable is not exploitable. The one candidate chain — a user file served from
  the web origin at `api/proxy/artifacts/[id]/download` — is blocked at each of
  these points, independently:
  `image/avif` is not in `ALLOWED_MIME` (415), the route returns 401 to the
  optimizer's cookie-less internal fetch, and artifacts are served
  `Content-Disposition: attachment` unconditionally.

**Do not round that to "we were never exposed."** The Windows advisory was live on a
dev host, and the optimizer's credential behaviour is taken from documentation
rather than from a request against a running instance — one `curl` settles it and
has not been run. That distinction is the difference between a patch record and an
incident record.

**Two accepted-risk items are open and blocked on a named owner, not on work.** Both
are installed-but-off-the-path with greppable firing conditions, written up in the
tracking issue: `ecdsa` (no fix version; both JWT paths pin non-EC algorithms) and
`sharp` (transitive under next only; no call path while the three image conditions
above stay at zero). An agent must not supply the name.

**One identification that was unresolved and is now settled**, because either half
alone reads as full coverage: the sharp CVEs (GIF/TIFF/VIPS loaders) and the libheif
overflow that the AVIF disable works around are **distinct**. Bumping sharp does
nothing for libheif; the AVIF disable does nothing for the other three.

### 2026-08-24 — the redaction boundary over-matched every "fl" word (#130, D-058)

`redact_for_ai` is the single LLM egress path, so `_redact_addresses` is the one
rule whose errors reach **every AI input in all five services**. Its
suite-designator pattern had no boundary after the keyword alternation and a
separator class that could match empty, so a keyword ate the rest of any word it
prefixed. Measured against `main` over one named corpus --
`tests/unit/test_redact_address_matrix.py::PRODUCT_NAMES`, 23 entries, six of
them negative controls -- so the ratio is reproducible from the repo rather than
from whichever list was to hand: **17 of 23 real security product names
corrupted** (`Stellar Cyber` -> `[ADDRESS] Cyber`; `Flowmon`, `Fleet`,
`Flashpoint`, `Steampipe`, `Aptible`, `Unitrends`, `Suitecrm` -> a bare
`[ADDRESS]`), plus prose, because security vocabulary is dense in "fl" -- flat,
flag, flaw, flow.

It failed silently: the model received plausible text, nothing raised, and no
test could see it -- **every name-shaped string in the seed and fixture data
passes the address rule clean**, so an assertion built on seed data passes
forever. Zero trips, counted twice with different nets: 73 on the original
hand-narrowed scan and 0 of 120 on a deliberately wide one. The two counts
disagree about what a "name-shaped string" is and agree on the number that
matters, which is why the property is stated here rather than the tally.

It also re-opened **#33 finding 5** through another door. Three products all
egressing as `[ADDRESS]` collide in `_by_alias_norm`, so the only string an
obedient model can cite resolves `ambiguous` -- and under **#102** that pulls the
technique out of the ATT&CK coverage **denominator**.

The rule is now decided by an enumerated **truth table** rather than a regex
patched case by case: `tests/unit/test_redact_address_matrix.py` -- six axes, accepted residuals
and standalone properties.

(This sentence carried a cell count and a breakdown summing to it. Both went
stale twice: 153 -> 327 when two sweeps were parametrised per separator, and <!-- counted: historical -->
327 -> 376 when the collector was actually run. A count in prose two files
away from the parametrisation that produces it is a derived value given a
second place to be wrong, so it is no longer derived here -- run the collector
if you need the number.) The
original table was written before the pattern, which is the method D-058
records; the rows added while fixing the street rule and while acting on the
adversarial review were not, and saying otherwise would make the method sound
more disciplined than it was. Three drafts were rejected on measurement,
including the issue's own suggested fix, which fixes less and leaks more.
Residuals are named and pinned rather than discovered later -- see **D-058**.

The street rule paid the same debt the suite rule did. `_STREET_PAT` kept `\s+`
through the first draft of the fix while the other two sub-patterns dropped it,
so it still reached BACKWARD across a line break and consumed a number belonging
to the previous line -- `Servers reviewed: 5` + a line break + `Main Street
office is unstaffed.` became `Servers reviewed: [ADDRESS] office is unstaffed.`, losing the count and
reading as ordinary prose afterwards. Narrowed to horizontal whitespace, with the
now-leaking wrapped address pinned as an accepted residual.

The separator narrowing was then wrong in the other direction, and the
adversarial review of the finished fix caught it. `\s` matches 19 horizontal
characters; the replacement enumerated three, so it silently dropped sixteen --
including the narrow-no-break and thin spaces that PDF and Word extraction emit.
A street address separated by one of those redacted on `main` and **egressed
verbatim** afterwards, with no `address` key in `removed_counts`: a leak at the
security boundary, strictly worse than the over-match being fixed, and invisible
because the decision was framed as being about newlines. The separator is now the
subtraction `\s` minus the ten characters `str.splitlines()` calls a line break,
and both halves are pinned as parametrised sweeps rather than sampled cells. See
**D-058**.

Filed as real issues, so no item hides another's cost and no claim here is a
claim about work nobody can find: **#138** (`street_pat` misses spelled-out and
alphanumeric house numbers -- `221B Baker Street` is untouched today -- and
leaves the trailing directional behind), **#139** (six designator keywords match
nothing at all), **#137** (the CAGE rule misses its own primary phrasing, so
`CAGE Code 1ABC2` leaks whole), **#136** (`_RE_CONTRACT` is compiled without
`IGNORECASE`, so a lowercase contract number leaks), and **#135**
(`_redact_signature_blocks` cuts everything from a bare `Thanks` or `Best` to end
of input -- data loss rather than a leak, and the one worth labelling). The
adversarial review then found the same newline defect one rule up, in
`_RE_PHONE`: a four-item numeric bullet list collapses to one token, a pair of <!-- counted: Describes the SHAPE of a test input, not a population that grows. -->
IP addresses is destroyed, and the audit row records `phone: 1` for input that
contained no phone number -- **#140**. `_RE_CAGE` has both halves of #130's
disease in one pattern (`CAGE codes are missing` -> `[CAGE] are missing`, and
`CAGE Code 1ABC2` leaks whole), tracked on **#137**.

`_RE_CONTRACT` is **not** the only pattern in the file compiled without
`IGNORECASE`, as an earlier draft of this entry said -- `_RE_EMAIL`, `_RE_PHONE`,
`_RE_SSN` and `_RE_EIN` are too. It is the only one where the omission changes
what matches, which is what was meant and not what was written.


### 2026-08-09 → 2026-08-17 — cross-service integrity (PRs #34, #35, #36, #39, #42, #45, #54)

An audit that began as an ATT&CK citation-resolver problem (#34) turned out not
to be an ATT&CK problem. Checking the other four services found **one defect <!-- counted: historical -->
family in ten places**:

> An AI-suggested value that fails validation is dropped silently, and the run's
> output is indistinguishable from a run where the model had nothing to say.

`docs/plans/2026-08-08-cross-service-integrity.md` (PR #35) is the **plan of
record**, with workstreams W0–W8. Read it before picking any of this up.

| PR | What landed |
| --- | --- |
| #34 | The ATT&CK citation-resolver plan, copied into the repo |
| #35 | The cross-service integrity plan (W0–W8) — plan of record |
| #36 | `adversarial-reviewer` onto `main` as a registered `subagent_type` (stop inlining it) |
| #39 | **F9** — ZT stamps AI provenance only when the AI actually changed the value |
| #42 | **W0** — CSF dimension-score edits are audited; the freeze stayed an open decision |
| #45 | **#41** — a top-level non-dict AI response is refused, not silently discarded |
| #54 | **W1, CSF step** — every AI suggestion is applied or itemized (**D-045**) |
| #56 | state-of-main refresh for the cross-service integrity stretch |
| #58 | **W4** — release assigns RELEASED to the parent and records which parent (**D-046**, migration 0041) |
| #63 | `CLAUDE.md`: a test that supplies its own expected value cannot fail |
| #66 | **W1, ZT step** — every AI suggestion applied or itemized; narrative fields removed (**D-047**, five adversarial rounds) |
| #78 | Shape guards on all four suggestion jobs + CSF hand-typed score protection (**D-048**, migration 0042) |
| #80 | **CSF client dashboard** — the last assessment service without one |
| #81 | `DELIVERY_PLAN.md` gains a living MVP completion path (order, status, blockers, sizes) |
| #82 | **Live-AI verification (#51)** — all five purposes run against a real provider; a corrupting-provider test reaches the drop paths fixture mode cannot |

**The AI layer has now run live.** A working provider key was installed
2026-08-19 and every purpose was exercised end to end with redaction confirmed.
Resting mode is back to `fixture`; live is opt-in per run (`pytest -m live`,
self-skipping without a key). What remains true is the reason it mattered:
fixture responses echo the parser's own keys back, so they can never express a
drop, a shape error, or a drift.

**These gates check whether a test can fail at all (D-051, PR #93).** The #72
pattern kept growing, and two of the instances were produced inside the audit hunting
for them. `scripts/check_test_integrity.py` is static and runs in CI ahead of
pytest; `scripts/mutation_sweep.py` runs nightly over changed files. Neither
closes #72 and D-051 says which instances each is blind to. Its first run filed
**#92**.

**W3 landed: approving a Tech Debt list now records WHAT was approved (D-053,
migration 0043).** An APPROVED list stays editable until release through five
doors, two of which change ATT&CK allow-list membership — a rename, and the
confirm queue that drops a row from security scope by design. The allow-list is
hard: a tool missing from it cannot be cited, so its technique reads as
uncovered. Approval now snapshots the security-scope membership and
`_client_tool_names` reads that; re-approval refreshes it, audited. **Closes #32
and unblocks W2.** One claim in the plan of record (§7's "Human-curated" pill)
does not hold on main and is corrected in D-053 rather than acted on.

**Tech Debt's audit closed #77 and stopped the reconciliation vanishing (D-052).**
Every registered job now carries a top-level shape guard — a sentence that could
not be written before. Separately, both surfaces measured the NAMED excluded
rows, so a provider that did not attribute every item to a source row produced no
disclosure at all and an unqualified "Total annual cost" over a partial figure:
the 2026-08-04 incident, reachable through the mechanism added to prevent it. The
count is now derived rather than measured off the named list, on the exporter and
the workspace together.

**Exports use the client's target and disclose what they omit (D-049).** #73,
#75 and #79 were one defect — `analyze_gaps` called without the target every <!-- counted: "were one defect" is an identity claim about two issues, not a tally. -->
other surface resolves — plus a truncation nobody disclosed. Both finalize audit
rows now record the target AND whether the client chose it, because a gap count
became uninterpretable the moment the target stopped being a constant. The
audit that gated it filed #84 (`risk.py` then compared against a hardcoded 3;
fixed, see below)
and #85 (self-assessment accepts a target intake rejects). Landed as PR #86.

**W8 is split and half of it is now in the MVP path (2026-08-20).** The #72
pattern reached **nine** instances, two of them produced inside the audit hunting
for them, minutes after the seventh was written down. W8a — the mechanised sweep
— becomes DELIVERY_PLAN item 2a; W8b, the adversarial reviewer as a CI job, stays
deferred with a stated reason (manual invocation is what caught every #86
finding; automating the working half is lower value than automating the failing
one). **#84 WAS folded into W1 Risk** rather than sequenced after it: it set the
input population of the very job W1 Risk instruments. **#87 is now decided (D-050): the contracted
target**, confirming what #86 shipped by implication. Confirming it surfaced a
gap it creates — **#90**, no consultant-side write path to that target exists
anywhere; the only two writes are in the client self-assessment submit. A
re-scope IS reachable — an admin cuts a new assessment version, which re-opens
the client's write — but that discards the completed assessment, since new
versions seed blank answer rows. That re-weights
**#85** from a narrow API edge case to the sole amendment path for the value
governing every deliverable. **#89** (the selector is exploration-only; Finalize
must surface the divergence) is a required follow-up, not optional.

**W1 is two services of four.** CSF (#54) and ZT (#66) are on `main`; Risk
and ATT&CK are outstanding, in that order, and ATT&CK is gated on W2 landing.
**SUPERSEDED 2026-09-21: W1 ATT&CK is item 7 and is complete; W1 Risk's
counters are persisted and read back, and what is left of item 6 is F10. See
the MVP path table in `DELIVERY_PLAN.md`, which is authoritative for item
status — this sentence is the record of where W1 stood when it was written.**
ZT removed its narrative fields rather than counting them — nothing consumed
them (#64) — and corrected D-045's false claim that ZT persisted them.

**W4 landed, and it unblocks W5.** That is the only ordering change `47b841f`
caused, and nothing recorded it until now. W0's freeze decision is also
unblocked, though it still needs Part 3 reopen scoped for CSF (which is W5).
Note D-046 is explicit that the lock W4 creates is PARTIAL: CSF's
`patch_dimension_score`, `profiles/seed` and `upsert_gap_action` still have no
parent-status guard. Its shape, settled on #44:

```
suggestions_received / suggestions_applied / dropped: [{reason, key, field, values, value}]
received == applied + sum(d.values for d in dropped)
```

Counted in **values** (one field on one row), not entries — **D-045** carries the <!-- counted: A definition of the unit of measurement, not a measurement. -->
reasoning and all four audit rounds. Itemized rather than counted because a
single integer cannot state its own scope, which is what sank the F9 counter
layer (see below).

**W0's freeze is an open decision and must not be reconstructed from memory.**
PR #42 shipped the audit row only; the three freeze guards were pulled because
25 of 25 approved CSF assessments have zero dimension scores — approval precedes
seeding universally, so freezing `seed_profiles` would leave the Playbook
permanently unexportable. The recommendation is due **after Part 3 reopen is
scoped for CSF**. Note the issue number cited for it in earlier handoffs (#37)
is **wrong**: #37 is closed and is the SEV-1 writable-RELEASED issue.

**W3 gates W2.** W3 = snapshot the exact tool-name set when a Tech Debt
capability list is approved, and have ATT&CK's "matched exactly, so confirmed"
read that snapshot. An APPROVED list is still editable, so narrow-confirmed is
unsound without it. **PR #29 is green and must not merge** until the W2 resolver
rewrite lands plus a clean adversarial audit.

#### Open follow-ups from this stretch

| # | What |
| --- | --- |
| #40 | ZT workspace has no lock control; the API supports it and ATT&CK/CSF ship it |
| #43 | `CsfDimensionScore` locked-row semantics + empty/null PATCH bodies |
| #46 | A response under the wrong top-level KEY is still silent — explicitly outside W1's invariant |
| #47 | `llm_calls` records COMPLETED for a response rejected after parsing |
| #51 | **W1's accounting has never been observed against a real provider — CSF _and_ ZT.** Fixture mode cannot produce a validation drop, so a green e2e proves nothing about it. Exact ZT scope: **six** of the eight reason codes need a live run to be seen at all (`entry_shape`, `unknown_key`, `unknown_field`, `unparseable`, `out_of_range`, `superseded`); `protected` is fixture-ONLY (`protected_keys` returns an empty set off-fixture) so it can never be observed live; `locked` needs no live run either — `build_zt_ai_request` sends every row including locked ones, so a fixture run over an API-locked row surfaces it end to end today |
| #59 | Release repair path is a permanent no-op for multi-version parents — `parent_version` never becomes known. **In scope for W5**, and the 0041 backfill has never run against data on any engine (the seed bypasses `release_deliverable` entirely) |
| #60 | `csf_score` requests an `executive_summary` on every call and nothing reads it — paid for, discarded, counted nowhere |
| #61 | W4's parent-flip log sits above its commit; the repair branch flips parent state with no audit row |
| #62 | `Service.released_at` is written only by the seed and read by nothing — settle with the deferred `ServiceStatus.RELEASED` question |
| #64 | ZT asked the model for three narrative fields nothing consumed (third instance of #60). Fixed in #66 |
| #67 | **CSF has no provenance protection** — an offline Run-AI silently overwrites hand-typed dimension scores where ZT protects the equivalent work. A recurrence of the 2026-08-04 incident (`provenance.py` records the numbers: a client's Identity pillar went 3.00 -> 1, unrecoverably). Not backlog |
| #69 | Admin live regions are mounted with their text, so failures announce and successes never do; `role="alert"` wraps an unbounded itemized list |
| #70 | `AttackWorkspace` marks its Run-AI step done for a run that applied nothing — the rule ZT adopted, unstated exemption |
| #71 | `csf.py` stores `what_we_found` unescaped — the one raw-model-string path the escaping fix did not reach, and the only durable one |
| #72 | **W8:** sweep for tests that cannot fail — five instances this session, two of which arrived AFTER the `CLAUDE.md` rule was written | <!-- counted: historical -->
| #73 | **Exported ZT deliverable ignores the per-capability AND intake targets**, exporting gaps against a default of 3 nobody chose; a stored target of 2 exports as 3. Pre-existing since the baseline import. **Next after this merge, ahead of W1-Risk** |
| #74 | CSF never received W1's severity model — a total loss to prompt drift still renders as a calm grey status line. Scoped matrix-first |
| #75 | Exported ZT Gap Plan truncated at 20 with `total_gap_count` rendered nowhere, while the on-screen view discloses it. Fix with #73 |
| #65 | `seed_demo.py` is all-or-nothing, not idempotent — one stray Service aborts the whole seed, so a drifted dev DB can never be repaired, and CI never hits it |
| #52 | `charged_likely` is true for auth-rejected calls that cannot have been billed (N-019 inverted, all four services) |
| #53 | `llm_calls` is flushed, not committed — any exception in the endpoint's post-call region discards a paid-for egress row, and the D-031 409 guard reaches it **by design** |

## Lessons learned (cross-service integrity)

- **A surfaced number that is wrong is worse than no number.** The F9 counter
  layer failed three consecutive adversarial passes while the provenance fix
  beside it passed four, so it was **deleted rather than shipped**. Once a banner
  exists, its absence reads to a consultant as "nothing was dropped" — which is
  exactly the claim a silent drop makes. That is why W1 is itemized: a single
  integer cannot state its own scope, so every wording of it is true for the case
  it was written for and false for an adjacent one.

- **Green CI never caught any of it.** Across F9 and W0, eleven adversarial
  passes ran and nine found real defects — six of those in the reviewer's own
  fixes — and two recommendations would have made things actively worse
  (un-locking seeded demo data; stranding 25 assessments). W1's CSF step then
  took four more rounds, every one of which found something. Not one of those <!-- counted: historical -->
  defects was caught by a test suite that was green throughout.

- **Budget four audit rounds per service, and do not read a flat defect rate as
  failure to converge.** W1's CSF step took four. Round 2 found that round 1's
  headline repair had re-opened the hole it closed; round 4 found the same of
  round 3. That is the process working correctly on itself, not the work failing
  to settle. ZT, Risk and ATT&CK should be planned with the same budget.

- **A guard against DOUBLE-counting becomes a guard against counting at all.**
  Twice in W1, a conditional added so a value would not be charged on both sides
  of the invariant created a path that recorded nothing. Both times it was caught
  by the round *after* the round that introduced it. The shape to watch: a
  conditional whose false branch drops the record instead of emitting it under a
  different reason. Now a rule in `CLAUDE.md`.

- **Changing copy for precision breaks whatever asserts it.** W1's panel line
  went from "suggested values" to "suggested **score** values" to be accurate
  about scope. The vitest was updated; `s7`'s regex was not — so the only
  end-to-end check of the feature could never have matched, and it would have
  failed as `element(s) not found`, the symptom this project has already
  misdiagnosed as a slow page and "fixed" with a longer timeout. Three
  independent reviewers found it; no gate did.

- **`int()` is not a validator.** `int(True)` is 1 and `int(1.9)` is 1, so a
  coercion sitting in a validation path wrote a value the model never sent,
  reported it as applied, and recorded nothing — silent handling inside the
  mechanism built to end silent handling.

- **A caveat that lives only in a code comment or a conversation will be lost.**
  Every limitation found in this stretch was filed as an issue, including the
  ones the author could have simply remembered: #51 exists because a green `s7`
  will otherwise read as proof of a feature fixture mode cannot exercise at all.

### 2026-08-08 — validation remediation (PRs #22, #23, #24)

The 2026-08-07 end-to-end validation run found 4 Critical defects; two more were
found while verifying the fixes. **All are now fixed and on `main`.**

| Finding | What it was | Fixed by |
|---|---|---|
| N-003 | Intake step 5 crashed the app — no client could submit | `a182a63` |
| N-014 | ATT&CK `mitre_map` failed 100% of the time; validated live at 633/633 after | `070af0d` + `9452604` |
| N-029 | Fixture run masqueraded as live and destroyed a client's answers | `a6fa0e1` |
| N-010 | Released report understated spend by $240,000 with no disclosure | `5e1f075` |
| N-030 | `/admin/deliverables` showed a raw 400 when no client was selected | `d03f119` |
| N-032 | Risk Register could never generate live (509 findings vs an 8192 cap) | `ef99e69` |
| N-033 | ATT&CK Run AI fabricated a 100%-gap assessment with no capability list | `ced76e4` |

Also landed: session refresh-rotation race fixed (concurrent requests were
logging users out mid-task), access TTL 15 min → 60 min, refresh TTL 30 min →
24 h, session-expiry warnings at 5 and 1 minute, and the ATT&CK workspace
reordered into numbered steps.

**Known-accepted risks are listed in `context/gene.md` under "Open concerns"** —
the live API key's cost exposure, the AI ledger being unfit for billing, and the
deliberate narrowing of refresh-token replay detection. None is resolved.


- **v2 work order (Parts A–F) merged to `main`** (PR #1, migrations 0015–0025,
  `v3.0.0`): all four service surfaces, multi-tenant onboarding, AI job
  registry, CSF Playbook engine, Risk Register, F hardening pass.
- **Sprint 1 "smoke sweep"** (PR #16, `v3.0.1`): `SMOKE_TEST.md` backed by a
  green Playwright smoke suite; offline fixture-mode AI (D-017), typed
  registration errors (D-016).
- **Sprint 2 "findings burn-down"** (PR #19, `v3.0.2`): 11 tasks, CI `e2e` job
  added.
- **Sprint 3 "audit correctness & honesty"** (PR #26, `v3.0.3`): 8 tasks burning
  down the 2026-07-08 deep repo audit.
- **Sprint 4 "framework majors + multi-provider LLM"** (PR #28, `v3.1.0`): the
  web stack moved to Next 15 / React 19 / Tailwind 4 / ESLint 9 / Node 22, and
  multi-provider LLM egress (OpenAI + Gemini beside Anthropic, D-024) landed
  below the unchanged redacting seam.
- **Sprint 5 "client value loop"** (PR #31, `v3.2.0`): consultant output now
  delivers visible value to the CLIENT role — deliverable release flow (D-025),
  `/home` executive dashboard + §2.5 value-loop card, `/documents`, a CSF POA&M
  step, a pre-egress redaction preview, and the first read surface over the
  append-only audit stores (`/admin/audit`).
- **Sprint 6 "real demo"** (PR #33, `v3.3.0`): the platform became a real,
  self-standing demo — runnable live-AI path with boot-time fail-loud (D-026),
  seed→MinIO storage parity, real TOTP MFA (D-027) + real email verification /
  password reset (D-028) on the custom-JWT stack (D-020 boot-refusals gone, flags
  now gate enforcement), a full-matrix `/ready` + `/admin/health` operator view,
  a coherent downloadable Atlas demo seed with one-command reset, and a
  hosted-demo production compose. Migrations 0030 (MFA TOTP) + 0031 (email
  tokens).
- **Sprint 7 "GCP live path + close the client loop" MERGED** (PR #36,
  `v3.4.0`): the live-AI path is now **proven against
  a real provider with no static key** — Vertex AI via Application Default
  Credentials (D-029), validated end-to-end across all five AI purposes on Dave's
  box (2026-07-15). The client loop is closed with a best-effort release
  notification email (D-030); dev/CI email delivery is on by default so the
  MailHog register/verify/reset loop is real every run (s21 runs, not skips); the
  Sprint-5 `reqSeq` stale-fetch guard sweep is finished; and the web auth stack
  migrated from next-auth v4 to Auth.js v5, clearing the `uuid@8.3.2` moderate
  advisory. No new migrations. New user-facing surface (release notification) + a
  real GCP live path justify the **minor** bump. Full exit gate set green — full
  Playwright e2e, `pytest -m unit`, web `tsc`, in-container web vitest (12/12),
  in-container web eslint (0 errors), host prettier `--check` (3.9.5), and
  in-container ruff/black.

### Sprint 7 task → commit

| Task | What shipped | Commit |
| --- | --- | --- |
| T0 | Vertex AI provider adapter via ADC — `VertexProvider` on `{region}-aiplatform.googleapis.com` generateContent, Bearer ADC (no static key), shared body-build/parse with `gemini`, token never logged, `live_llm_readiness()` boot preflight; D-029 | `7dcf159` |
| T1 | GCP live validation sweep (opt-in) — all five purposes live on `vertex`/`gemini-2.5-flash` (ADC-only) through the redaction seam; found+fixed 2 adapter defects (`google-auth[requests]`; loud `finishReason` guard + cap 4096→8192 + `thinkingBudget` for 2.5+); SMOKE §14/§14.1 GCP-annotated | `329f9a5` |
| T2 | Client release notification email — shared release helper emails the tenant's active client users on release (best-effort, release is source of truth); D-030 | `4420b53` |
| T3 | Email delivery on by default in dev/CI compose (MailHog); s21 email-verify now RUNS instead of self-skipping; REQUIRE_EMAIL_VERIFY stays off | `d95f5c7` |
| T4 | reqSeq stale-fetch guard sweep remainder (Sprint-5 carry-over) across admin workspaces/panels; guards only where a stale mount-fetch clobbers newer state; two vitest guards | `37f9bd6` |
| T5 | Auth.js (next-auth) v5 migration — `getServerSession`→`auth()` at 34 sites, MFA code-signal re-wired, behavior-identical; clears the `uuid@8.3.2` moderate | `3de0626` |
| T6 | Wrap-up: SMOKE §14 GCP annotation / §25 checked / new §29 release-notification, CHANGELOG `[3.4.0]`, BUILD_REPORT sync, DECISIONS D-029/D-030 verify, full gates, this snapshot | `4796429` (PR #36 squash) |

No new migrations this sprint. New DECISIONS: **D-029** (Vertex AI via ADC as the
GCP live path) + **D-030** (client release notification, best-effort notify).

- **Sprint 8 "prove it in the browser" MERGED** (PR #42,
  `v3.4.1`): eight tasks (T0 through T7) that convert
  human-eyeball SMOKE debt into committed Playwright specs and pay the last
  mint-route debt. The release notification is now eyeballed in MailHog (§29,
  s22), the verify/forgot/reset pages and the MFA enrollment / TOTP / recovery-code
  UI are browser-driven (s23, s24), `/admin/health` and the `/documents` empty
  state have specs (s25, s17), and a double-POST to the tech-debt extract route
  reuses the open draft instead of burning a second LLM call (T1). The sprint's
  headline was an out-of-plan product fix: **MFA sign-in never revealed the TOTP
  field in the browser** because `SignInForm` sent `totp: undefined`, which
  next-auth coerced through `URLSearchParams` into the string `"undefined"`,
  defeating the backend `!totp` guard (fixed in `f10b803`; the new T4 browser spec
  caught what the Sprint-7 vitest could not). No migrations, no new DECISIONS.
  Version is tag/CHANGELOG level only; package manifests untouched. Plan was
  reviewed read-only by OpenAI Codex pre-merge (findings table in PR #37).

### Sprint 8 task → commit

| Task | What shipped | Commit |
| --- | --- | --- |
| T0 | Shared MailHog reader helper (`e2e/helpers/mailhog.ts`): `fetchLatestMessage` / `extractToken` / `subjectOf`, polls by recipient plus subject; s21 consumes it with zero behavior change | `3b7bfb7` |
| T1 | Tech-debt extract draft-exists guard: a second POST while a draft is open returns it idempotent-200 before the LLM call (no re-extract, consultant edits survive), matching CSF/attack/zt; `test_extract_versions_subsequent_lists` re-contracted to the APPROVED/RELEASED boundary | `4396f60` (+ e2e realign `b4fe0ba`) |
| T2 | `s22-release-notify.spec.ts`: isolated tenant + unique-email client, release a CSF deliverable, assert the notification in MailHog by recipient + subject + `/documents` link (SMOKE §29) | `d023226` |
| T3 | `s23-auth-pages.spec.ts`: browser-drive verify-email / forgot-password / reset-password pages end to end, then sign in with the new password | `442fca5` |
| T4 | `s24-mfa.spec.ts` part A: enroll on `/account` with a generated TOTP (otpauth dep), assert shown-once recovery codes, sign in through the UI TOTP step. **Surfaced the MFA sign-in browser bug** | `f70a8cc` (fix `f10b803`) |
| T5 | `s24-mfa.spec.ts` part B: redeem a recovery code at sign-in, prove it single-use on reuse. T4+T5 retire the manual MFA walkthrough | `1e782de` |
| T6 | `s25-admin-health.spec.ts` asserts the all-green `/admin/health` matrix on the live stack; `s17-documents.spec.ts` gains a `/documents` empty-state assertion in a fresh throwaway tenant | `57277ea` |
| T7 | Wrap-up: SMOKE annotations, CHANGELOG `[3.4.1]`, BUILD_REPORT sync, this snapshot, `context/dave.md` refresh | `b7d482d` |

No new migrations and no new DECISIONS this sprint: T1 applies the existing
CSF/attack/zt idempotency pattern, and MFA (D-027), email verify/reset (D-028),
and the release notification (D-030) all shipped earlier and were only proven in
the browser here.

- **Sprint 9 "activate the seam" COMPLETE on its branch** (`feat/sso-discard-demo-sprint-9`,
  targeting `v3.5.0`): eleven tasks (T0 through T10) across three themes. The
  long-dormant Keycloak seam is now a working hybrid OIDC sign-in beside the
  credentials form, flag-gated behind `SHIELD_AUTH_OIDC_ENABLED` and default off
  (D-032, migration 0032 `users.keycloak_sub`). The browser round trip ends at
  `POST /auth/oidc/exchange`, which verifies the Keycloak access token against the
  realm JWKS (RS256-only, `iss`/`aud`/`azp` pinned) and mints a native SHIELD HS256
  pair only for an already-active local account. A Keycloak token is never accepted
  as an API bearer; the backend keeps minting its own JWTs (D-020 stays
  authoritative); there is no JIT provisioning. With the flag off the provider does
  not exist and zero Keycloak network calls happen. Every service also gained a
  first-class draft-discard affordance (D-031): a draft-only admin `POST .../discard`,
  the app's first destructive-confirm dialog, the version trap closed, and the
  hidden latest-consumers (risk synthesis, engagement cards) skipping discarded
  rows. The demo compose and the export eyeball debt are now under committed
  automation (D-033): the five SMOKE §10 export checks are unit assertions over real
  PDF/DOCX/XLSX bytes, and `demo-reset --demo` plus `e2e/demo/demo-journey.spec.ts`
  and a new CI `demo` job prove the hosted-demo bring-up. Minor bump for the two new
  flag-gated user-facing surfaces; tag/CHANGELOG level only, package manifests
  untouched. Plan was reviewed read-only by OpenAI Codex pre-merge (verdict
  "rework" on 12 findings, 2 blockers, all folded into the tasks).

### Sprint 9 task → commit

| Task | What shipped | Commit |
| --- | --- | --- |
| T0 | Backend draft discard ×4 + `DISCARDED` status; version trap closed (`_latest_*` skip discarded, mint reads unfiltered `max(version)`); risk synthesis + intake cards skip discarded; conditional-UPDATE concurrency contract; D-031 | `638710c` |
| T1 | Web discard UI: 4 proxies, client fns, shared `DiscardDraftButton` + design-system Modal (first destructive-confirm dialog), `reqSeq` bump before post-discard refetch | `578a98a` |
| T2 | Export-content unit assertions over real bytes (pypdf test dep; PDF/DOCX/XLSX readers); SMOKE §10 re-pointed + one manual aesthetics line; §19 closed | `af4dcf3` |
| T3 | e2e: the three approve-first preambles (s4/s5/s11) now discard via proxy, post-preamble assertions byte-identical; s4 drives the UI discard once; SMOKE §31 | `56bcfce` |
| T4 | Backend OIDC: flag + `oidc_readiness()`, JWKS verifier (RS256-only, cache/TTL/lock), `POST /auth/oidc/exchange` typed-failure matrix, TOFU sub binding, migration 0032; D-032 | `60d2abb` |
| T5 | Infra: dual-horizon Keycloak (`KC_HOSTNAME` + backchannel-dynamic, one canonical iss), realm drift fixes, env plumbing, real flag-gated `/ready` probe | `4c9ab64` |
| T6 | Web OIDC: conditional secret-less PKCE provider, jwt-callback exchange branch, sign-in button, `SessionExpiryGuard` failure path; flag off is a behavioral no-op | `ca0093b` |
| T7 | Opt-in `s26-oidc-login.spec.ts` (positive + negative through the real Keycloak form, self-skips unless `E2E_OIDC=1`); SMOKE §32 | `1e3e64e` |
| T8 | Demo-reset `--demo`/`-Demo` mode (sh/ps1 parity) + fail-loud web-wait; opt-in `e2e/demo/demo-journey.spec.ts`; SMOKE §26; D-033 | `8b5e68a` |
| T9 | CI `demo` job on its own isolated runner (compose-version floor, `demo-reset --demo`, `SHIELD_DEMO_SMOKE=1` playwright, always-run diagnostics + artifact upload); SMOKE §27 | `00d970e` |
| T10 | Wrap-up: SMOKE final pass (§10/§19/§26/§27/§31/§32), CHANGELOG `[3.5.0]`, BUILD_REPORT sync, this snapshot, `context/dave.md` refresh, full gates + full e2e | `ee8bf23` |

One migration this sprint: **0032** (`users.keycloak_sub` String(64) nullable <!-- counted: historical -->
unique, additive/SQLite-safe, C0). New DECISIONS: **D-031** (draft discard as an
admin-only soft-delete state transition), **D-032** (hybrid Keycloak SSO as a
flag-gated exchange, never a bearer), **D-033** (destructive-by-design automation
is opt-in-gated).

- **Seven-issue fix pass MERGED** (PR #5, was `fix/seven-issue-pass`, targeting <!-- counted: The NAME of a past pass, and the literal branch name. Rewording it would make the record harder to find, not more accurate. -->
  `v3.8.0`): seven reported issues in four phases. Three were the same class of
  defect — a surface that renders but cannot be acted on. The client `/home`
  service cards were unlinked `Card`s, so a client could see a service and had no
  way to open it; `/admin/active` was a stub whose body was one "go elsewhere"
  button; and the skip-to-content link moved focus correctly but showed nothing,
  because `outline-hidden` on all 8 `main#main-content` shells cancels the ring
  that `focus:outline-2` sets up. The headline defect is issue 4: **nothing in the
  product could release a deliverable**, so the D-035 client dashboards' release
  gate was unsatisfiable and no client could ever see a dashboard — three stacked
  bugs (a client function with zero callers, a missing Next proxy route, and a TS
  field name that never matched the API's `released_at`). Admin removal
  (soft-archive a tenant, deactivate a user) and a runtime provider-API-key panel
  round out the pass. Two additive migrations, **0033** (`client.archived_at`) and
  **0034** (`llm_credentials`). New DECISIONS: **D-036** (soft removal + `/auth/login`
  now honours `is_active`), **D-037** (runtime keys, validate-then-store, DB beats
  env), **D-038** (release control + admin pre-release preview through the shared
  builder).

### Seven-issue pass: issue → commit <!-- counted: The same proper name, used as a heading. -->

| Issue | What shipped | Commit |
| --- | --- | --- |
| 1, 5, 6 | `/home` service cards are links routed by phase (`dashboardPathFor()` as the one source of truth, shared with `/documents`); `/admin/active` redirects to the queue and leaves the nav; skip-link focus ring made visible | `c6eb34a` |
| 1, 5, 6 | Follow-up after in-browser verification: `outline-hidden` was cancelling the ring the first commit added — removed from all 8 shells; specs `s31`, `s35`, extended `s12` | `eaaa060` |
| 3, 7 | `DELETE /admin/clients/{cid}` (soft archive, migration 0033), tenant user list, `PATCH /admin/users/{uid}`; `/auth/login` `is_active` gate + refresh-jti clear; `/admin/queue` as an org index with `/admin/queue/[clientId]`; `test_admin_removal.py`, `s32`, `s33` | `a54cfb0` |
| — | Bandit `# nosec` marker CI needed on the dev artifact path | `6ad9cfb` |
| 2 | `POST`/`DELETE /admin/llm-key` (validate against the provider, then store Fernet-encrypted, migration 0034); `AiStatusBanner` moved into the admin shell; `LlmKeyPanel`; `RunAiGuard`; `.env` placeholder model corrected; `test_admin_llm_key.py`, `RunAiGuard.test.tsx`, `s34` | `006f571` |
| 4 | Release wired end to end for all four services (callers + 4 proxy routes + `released_at` type fix), admin pre-release preview via the shared `_dashboard_deliverable()` resolver, `resolveDashboardClientId()` for cold admin URLs, single-body-read fix in all six client libs; `s36` | `c601d32` |

- **Seven-issue pass and UX-findings remediation MERGED** (PRs #5, #6, #7, #8): <!-- counted: The same proper name. -->
  the pass described below landed, along with the 2026-08-04 UX/E2E remediation
  (audit-mode correctness, a failure record that survives the request rollback,
  the offline Run-AI guard on every entry point, extraction reconciliation,
  bundle decomposition, date-only rendering, dashboard `<main>` landmarks). PR #7
  separately repaired a `pnpm-lock.yaml` that was missing `chart.js` /
  `react-chartjs-2`, which had been failing CI on **every** branch.

- **Portfolio scope, derived stages, and intake contact MERGED** (PRs #9, #10;
  migrations **0038**, **0039**): three decisions, D-039 through D-041.

  **Tech Debt now covers the whole software portfolio.** The v1 prompt kept only
  security capabilities and dropped the rest silently — the guided review
  uploaded 21 rows / $1,634,236 and the workspace showed 12 / $891,796 as though
  that were the inventory. Prompt v2 classifies every row instead. That moves the
  risk rather than removing it: `valid_tools` in the ATT&CK mapping is a hard
  allow-list on what the model may cite, so a wrong "not security" call makes a
  tool *uncitable* and its technique reads as uncovered rather than unassessed.
  A negative is therefore provisional until a consultant signs off (D-039).

  **One six-stage vocabulary across all four services**, derived read-only from
  status plus evidence, changing no state machine (D-040). The version trap is
  real and was hit twice: `llm_calls` has no version link, and Tech Debt builds
  its list *after* the run that produced it, so the timestamp anchor that works
  for the other three matches nothing there.

  **The intake contact belongs to the engagement**, not to whoever filled in the
  form (D-041).

  Notable process point: **the browser check found a defect in every one of the
  four rounds**, including two the unit tests could not see (the monotonic-stage <!-- counted: historical -->
  cursor, and stage evidence for Tech Debt). The e2e specs written afterwards
  found two more. See "Lessons learned (portfolio scope + stages)" below.

- **CI hygiene MERGED** (PR #10): the gitleaks job had failed on **every** PR
  since it was added, with a 403 "Resource not accessible by integration" — the
  workflow default is `contents: read` and gitleaks writes findings back to the
  PR. Job-scoped `pull-requests: write` fixes it. Dependabot PRs still 403 by
  GitHub's design, and that caveat is recorded in the workflow. `s11-staleness`
  also stopped sharing the seeded ATT&CK service with `s5` (it raced for it *and*
  approved/finalised it, changing state every later spec inherited).

### UX findings burn-down — COMPLETE (`main` at `a9ec90f`, 2026-08-07)

`UX findings.docx` (22 numbered findings + a "Recommended page structure"
appendix) and the 2026-08-04 guided live run (`REPORT.md`, F-1..F-12, outside the
repo at `e2e-review-20260804-211926/`) are both **fully burnt down**. The two
documents overlap heavily; PR #6 carries the authoritative change -> finding table.

| Phase | PR | Findings closed |
| --- | --- | --- |
| — | #5, #6 | UX 1, 2, 3, 6, 10, 11, 12, 13, 14, 19, 20, 21, 22 + F-1..F-12 (F-10 **withdrawn**: a measurement artifact of the review harness, not a defect) |
| A | #9, #10 | UX 4 (disclosure + portfolio scope), UX 16 (D-039, D-040) |
| — | `2552dca` | UX 5 (bundle decomposition, migration 0037) |
| B | #11 | UX 8, 9 (D-041) |
| C1 | #12 | UX 15 |
| C2 | #14 | UX 18 (**D-042**) |
| C3 | #15 | UX 17 (**D-043**) |
| D | #16 | IA appendix: admin Deliverables (**D-044**) |
| D | #17 | IA appendix: queue filters, Risk Register scope; plus six stale "Back to documents" labels C2 missed |
| D | #18 | IA appendix: Help surface + shared `SERVICE_DESCRIPTIONS` |
| — | #19 | `s34`'s Run-AI-guard test made unconditional |

**No migrations in Phase C or D.** The Deliverables statuses derive from columns
that already existed.

**Superseded 2026-08-19.** Live-AI verification completed — item 0 in
`DELIVERY_PLAN.md`, tracked as #82 — so the instruction at the end of this
paragraph no longer applies. Kept as the record of Phase D's close.
<!-- counted: historical -->

**The one open item was a verification gap, not a defect.** `REPORT.md` records
that CSF and MITRE live scoring were never completed, deprioritised once F-3 was
established, and F-3's own note says Zero Trust could not complete on live
Anthropic at all. PR #6 added streaming to answer that — but **nothing has
re-proven ZT, CSF or MITRE against live Anthropic since**. Sprint 7's live
validation (2026-07-15) was on **Vertex/Gemini**, a different adapter with a
different failure mode. On the default provider exactly one purpose
(`extract.capabilities`) has ever completed live, and that was before the
streaming change. Treat "live Anthropic works" as unproven until a run says so.

### Portfolio scope + stages: change → commit

| Change | What shipped | Commit |
| --- | --- | --- |
| D-039 | Prompt v2 classifies every row; `security_scope.py` fail-safe rule; confirm/override endpoints; `_client_tool_names` status filter; migration 0038 | `faa8a78` |
| D-040 | `services/stages.py` + `/services/{id}/stages`; `ProgressStages` in four workspaces; `useServiceStages` phase-explicit hook | `faa8a78`, `576f0f6` |
| e2e | `s37` sign-off queue, `s38` stage bar — which found the empty-service and Tech-Debt-ordering bugs | `569984b` |
| CI + isolation | gitleaks permissions, `s11` mints its own service, fixture skips unnameable rows, `s39` excluded-rows queue | `bd653b0` |

## Lessons learned (portfolio scope + stages)

- **A filter that decides what an AI may cite is not an input, it is an
  assertion.** `valid_tools` reads like prompt plumbing. It is actually the list
  of names the model is *allowed* to say, so anything missing from it produces a
  gap the report presents as assessed. Any narrowing of that list needs a human
  in front of it, and it must fail toward inclusion.

- **`None` is not `False`, and collapsing them loses data silently.** An
  unclassified capability is the absence of a decision. Treating it as a negative
  would have dropped every pre-migration inventory out of ATT&CK with nothing
  failing and no error anywhere.

- **The same trap has two different shapes in one codebase.** Stage evidence had
  to be version-anchored — and then Tech Debt turned out to build its version
  *after* the run that produced it, so the anchor that was correct for three
  services matched nothing for the fourth. "We fixed the version trap" was true
  and incomplete; only the e2e spec showed the second half.

- **A hand-written serializer will drop a new column, twice.**
  `_serialize_list_with_items` silently omitted `source_rows_total`, then
  `confirmed`, each reading as null in the UI with nothing failing — the second
  time despite a comment warning about the first. It now builds from the model.

- **An unreachable review surface is an untested one.** The excluded-rows queue
  could not appear in fixture mode because the fixture invented a name for every
  row, so no exclusion could ever exist. The same hole hid the security sign-off
  queue. Both were closed by making the fixture behave like the prompt it stands
  in for, not by writing more tests around the unreachable state.

- **Run the browser check before believing the tests.** Four rounds, four <!-- counted: historical -->
  defects it caught that unit tests and typecheck did not: a null
  `source_rows_total`, a monotonic-stage cursor rendered behind completed work,
  an override stored but absent from the response that had to restore it, and a
  400 on every stage call in the admin queue (tenant resolved from an
  active-client cookie while the page was scoped by path).

- **A check that is always red is worse than no check.** gitleaks failed on every
  PR for a permissions reason unrelated to any diff. That is not a nuisance —
  it trains everyone to skip the one signal that matters the day it is real.

- **A helper that gives up silently costs more than one that throws.**
  `acknowledgeOfflineAi` waited 4s for the offline dialog, returned quietly when
  it did not appear in time, and left the caller waiting two minutes for a
  request that would never be sent — failing with "timeout waiting for response",
  which points at the API instead of the un-clicked button. Diagnosed twice
  before the cause was found.

## Machine-local facts (this box)

- **Web runs on port 3001**, not 3000: root `.env` `WEB_PORT=3001` /
  `NEXTAUTH_URL=:3001` (a separate next-dev holds `:3000`). Playwright resolves
  the port via `e2e/helpers/baseUrl.ts` — never hardcode `:3000` in new specs.
  Canonical/CI stays `:3000`.
- **gh CLI has two accounts:** active `SpearheadAnalytica` (full write) and
  `david-catarious_kentro` (Kentro EMU — reads only; GitHub blocks EMU writes
  outside its enterprise). `gh auth switch --user <name>` to flip; `git push`
  authenticates as SpearheadAnalytica via GCM regardless.
- **Tooling not on default PATH:** `node.exe` + `gh.exe` live under
  `%LOCALAPPDATA%\Microsoft\WinGet\Packages`. Run e2e via that `node.exe` +
  `e2e/node_modules/@playwright/test/cli.js`. Docker CLI needs
  `export PATH="$PATH:/c/Program Files/Docker/Docker/resources/bin"` per shell.
  Host Node LTS is 22 (matches the container after Sprint 4 T4).
- **Six queue gates:** `pytest -m unit`, web `tsc`, host prettier `--check` **at
  whatever version your runtime `.claude/sprint-queue.json` pins — re-sync it
  from a staged queue after any prettier bump, because it is gitignored and no
  PR can change it** (staged queues say `3.9.6` as of this commit; a runtime
  queue copied before it still says `3.9.5`), in-container ruff/black (root-config parity), in-container web vitest
  (`pnpm -F web test`), in-container web eslint (`pnpm -F web lint`). Bandit is
  CI-only (a ruff `# noqa` does NOT suppress it — a flagged string needs its own
  `# nosec`).
- **GCP live path (Sprint 7):** live Vertex needs `SHIELD_LLM_MODE=live`,
  `SHIELD_LLM_PROVIDER=vertex`, `SHIELD_LLM_MODEL=gemini-2.5-flash`,
  `GCP_PROJECT_ID=kentro-cloudmod-dev`, `GCP_REGION=us-central1`, and host gcloud
  ADC bind-mounted read-only (`GCLOUD_CONFIG_DIR`, `%APPDATA%\gcloud` on this box)
  with `GOOGLE_APPLICATION_CREDENTIALS` pointing at the mounted file — all in the
  **gitignored** `.env`, reverted to fixture after validation. There is NO static
  Google API key anywhere. Adding `google-auth` (T0) required
  `docker compose build api` — a plain restart won't install it.
- **Framework/module reinstall dance:** after editing any `apps/web` source,
  `docker compose up -d --force-recreate web` before any e2e (next-dev hot-reload
  does not fire through the Windows bind mount). After `apps/web/package.json`
  changes (Sprint 7 Auth.js v5), reinstall INSIDE the web container. A NEW python
  module under `app/` needs `docker compose restart api`; NEVER restart api while an
  in-container pytest is running (SIGKILL 137).
- **Hybrid OIDC flag is default OFF and must never be committed on** (Sprint 9,
  D-032). `SHIELD_AUTH_OIDC_ENABLED=true` in the repo-root `.env` plus
  `docker compose up -d --force-recreate api web` (web reads it at provider
  registration, api at boot readiness) turns it on; a realm-export change since the
  last import also needs a keycloak volume wipe
  (`docker compose stop keycloak && docker volume rm shield-v2_keycloak-data && docker compose up -d keycloak`).
  The `s26-oidc-login` opt-in spec runs with `E2E_OIDC=1`; always restore the flag
  off and re-prove one credentials sign-in afterward. The realm now pins one
  canonical issuer (`http://localhost:8080/realms/shield`) for browser and
  containers via `KC_HOSTNAME` + backchannel-dynamic; the api fetches JWKS on the
  `keycloak:8080` horizon.

## Deferred / needs a human

- **SMOKE_TEST §14 / §14.1 — GCP-validated 2026-07-15 (Sprint 7 T1):** the
  opt-in `@pytest.mark.live` specs were run for real against Vertex (ADC-only)
  across all five purposes; still self-skip keyless so CI/loop stay green without
  credentials. Re-verify with a keyed/ADC run.
- **SMOKE_TEST §29 (release notification), done in Sprint 8 T2:**
  `s22-release-notify.spec.ts` now reads the notification out of MailHog for a real
  registered client of an isolated tenant, matching on recipient, subject, and the
  `/documents` link, on top of the four `test_release_notification.py` unit tests.
- **SMOKE_TEST §10 (export content) closed in Sprint 9 T2:** the five eyeball
  boxes are now unit assertions over real bytes (PDF via `pypdf.PdfReader`, DOCX via
  `docx.Document`, XLSX via openpyxl). One explicitly-manual line remains, deferred
  by design: visual aesthetics only (cell shading, heatmap colors, spacing,
  page-breaks), which no test can assert.
- **CI `demo` job green-run pending the first PR (Sprint 9 T9):** the `demo` job
  in `.github/workflows/ci.yml` is green locally (T8's destructive proving run) and
  YAML-validated, but this repo's CI triggers only on push/PR to `main`, so its
  first green CI run is cited when the dev opens the sprint PR. SMOKE §27's CI-job
  box stays annotated "pending first PR run". Same posture as the `e2e` job.
- **`sharp <0.35.0` HIGH advisory (needs Dependabot / a human):** a new root
  advisory (libvips CVEs), transitive via next@15's image optimizer, NOT introduced
  by this branch and not exploitable in our use (no untrusted image processing). Not
  fixable without a lockfile bump, which Sprint 9 deliberately did not touch.
  Recommend a Dependabot bump or a root pnpm override on `main`.
- **MFA / email web UI eyeball, done in Sprint 8 (T3 through T5):** the sign-in
  MFA step, the enrollment section, and the verify/forgot/reset pages are now
  browser-driven (`s24-mfa.spec.ts`, `s23-auth-pages.spec.ts`); the manual MFA
  walkthrough is retired.
- **Hosted-demo + demo-reset, automated in Sprint 9 (T8/T9):**
  `demo-reset --demo`/`-Demo` plus the opt-in `e2e/demo/demo-journey.spec.ts` and
  the CI `demo` job now drive the hosted-demo bring-up; the manual-only note is
  retired (the destructive proving run is opt-in-gated per D-033).
- **ESLint 10** — deferred upstream (D-018 dated deferral): no published Next lint
  stack runs on it today.
- **One documented moderate audit finding** left deliberately open: `postcss`
  8.4.31 (pinned in `next@15`; XSS-stringify path N/A at build). Clears on the next
  upstream Next bump. The npm audit HTTP endpoint 410s upstream; posture verified
  from the lockfile dependency graph.
- **Needs David (cloud infra + full federation):** `infra/terraform`
  (cloud/account/region/network) and DR runbooks are stubs; FedRAMP-authorized LLM
  connector; `azure_openai`/`bedrock`/`local` LLM adapters stay loud
  not-implemented. The Keycloak SSO deferral is LIFTED at hybrid depth (Sprint 9
  D-032): OIDC sign-in works flag-gated. Full token federation (the backend
  accepting Keycloak tokens as API bearers), JIT user provisioning, migrating
  register/MFA/email flows into Keycloak, an un-discard/recovery endpoint (DISCARDED
  is terminal in v1; rows stay DB-recoverable), and stamping local
  `email_verified_at` from a Keycloak claim all stay out of scope. Dave's 2026-07-13
  call: local containers for now.

## Test coverage status

- Backend: full `pytest -m unit` green in-container. Sprint 9 added
  `test_discard_draft.py` (the four-service discard contract: draft-only 200 +
  single audit row, idempotent re-discard, 409 on SUBMITTED/APPROVED/RELEASED, 403
  client, 404 cross-tenant, the version-trap regression, the hidden latest-consumers
  in `risk.py`/`intake.py`, and the discard-then-stale-write concurrency contracts —
  the end-of-sprint audit pass rounded the file out to full four-service symmetry:
  tech-debt child-mutation-after-discard 409, plus csf/zt idempotent re-discard);
  `test_oidc_exchange.py` (an in-test RSA keypair signs Keycloak-shaped tokens, a
  monkeypatched `_fetch_jwks` returns the matching JWKS, and the full rejection
  matrix plus TOFU sub-binding is exercised); the export-content tests (T2, real
  PDF/DOCX/XLSX bytes); and the readiness-probe cases (T5, flag-off dormant /
  flag-on ok/down, `ready` never gated by keycloak). Sprint 7's Vertex adapter and
  release-notification suites and the opt-in `tests/live/test_live_ai.py`
  (`@pytest.mark.live`, excluded from `-m unit`, GCP-validated 2026-07-15) are
  unchanged.
- Web unit tests: `pnpm -F web test` (vitest) **116/116 across 22 files** on
  `a9ec90f`. Phase C/D added `HomeDashboard` bucket + primary-action cases,
  `DeliverablesTable.test.tsx`, and `lib/admin/filters.test.ts` (the queue filter
  predicates, including the future-timestamp case). Earlier: 37/37 across 10 files. Sprint 9 T1
  added `DiscardDraftButton.test.tsx` (renders only for a draft, opens the Modal,
  confirm invokes the callback, cancel/ESC/backdrop are no-ops) and `CsfWorkspace`
  discard tests (the answered-count warning line, plus the end-of-sprint audit pass's
  onDiscard main-path test: confirm → `discardAssessment` → guarded refetch clears the
  workspace to the empty state); T6 added `oidc.test.ts` (isOidcEnabled truth table + rewrite/passthrough),
  `KeycloakSignInButton.test.tsx`, and `SessionExpiryGuard.test.tsx` (signs out on
  `OIDC_EXCHANGE_ERROR`). The Sprint-8 `SignInForm` omit-totp guard and the reqSeq
  guards remain.
- Web `tsc --noEmit` clean on Next 15 / React 19 / Tailwind 4 / Auth.js v5. ESLint
  0 errors (1 pre-existing postcss warning). In-container `pnpm -F web build` was
  proven green in T6 (the standalone prod image the demo compose runs).
- e2e: **41 spec files** (host; `:3000` on Gene's box, `:3001` on Dave's). Phase
  C/D added `s40-admin-deliverables` and `s41-help`, and rewrote `s34`'s
  Run-AI-guard test to seed its own tenant so it can no longer self-skip.
  **Numbering caution:** `s37`/`s38` were briefly duplicated when the Phase D
  specs were added without checking the directory — renamed to `s40`/`s41` in the
  same pass. `s12` carries a genuine pre-existing duplicate
  (`s12-a11y-nav`, `s12-notfound`). Check `ls e2e/smoke` before claiming a number.
  Earlier: 27 spec files. Sprint 9 added `s26-oidc-login`
  (opt-in, self-skips unless `E2E_OIDC=1`) and `demo/demo-journey` (opt-in,
  self-skips unless `SHIELD_DEMO_SMOKE=1`), so the default suite count is unchanged.
  The T10 exit run was green on the flag-off dev stack: 51 passed / 6 skipped (2
  s26 + 4 demo-journey), zero failures/flakes, across six foreground sub-9-min
  shards. Known cold-compile flake under load documented in `CLAUDE.md`; per-spec
  standalone is the flake arbiter.
- Format: repo-wide prettier `--check` clean at 3.9.5. Python ruff/black clean
  (root-config parity).
- Audit: bandit CI-only, exit 0. Root `pnpm audit` posture: one new documented
  `sharp <0.35.0` HIGH (libvips CVEs, transitive via next@15's image optimizer, not
  branch-introduced, not exploitable in our use) plus the standing `postcss`
  moderate; both blocked on a lockfile bump this sprint did not touch (Dependabot /
  root override on `main`). The `uuid@8.3.2` moderate cleared in Sprint 7 T5. No
  secret / token committed this sprint (the secret-less PKCE client meant the T6
  dev-realm fallback secret was never needed).

## Lessons learned (Sprint 9)

- **Activating a state means auditing every reader, not just the writer.** Adding
  `DISCARDED` was the easy part. Codex's two blockers were both hidden consumers: <!-- counted: historical -->
  the risk-register synthesis has its own `_latest()` that would have read a
  discarded highest-version assessment straight into the gate, and the intake
  engagement cards reported the raw latest version. A dormant status is only as safe
  as the query that forgot about it. The rule that fell out: when a new row state
  goes live, grep for every "latest" and every parent-state guard across the whole
  codebase, not just the four route files that mint the state.
- **The version trap is a real IntegrityError, not a hypothetical.** The
  `_latest_*` helpers must skip `DISCARDED` (so a discarded draft is invisible to
  consumers) while the mint's next-version computation must read `max(version)`
  unfiltered (so it does not reuse the discarded version's number and collide on the
  `(service_id, version)` unique constraint). Getting the second half wrong throws
  on the first re-extract after discarding a non-v1 draft. The regression test runs
  on an alembic-upgraded SQLite fixture precisely so the unique constraint is real,
  not mocked away.
- **A mocked unit test cannot prove a flag-off no-op or a beta integration.** T6's
  hardest promise was that flag-off changes nothing, and the only honest proof is a
  vitest trap that fails on an unexpected Keycloak fetch. The throwaway auth-code
  spike then caught a bug no unit mock could: a rejected exchange left the token
  without an access token, so the next `jwt` call fell into `refreshAccessToken()`
  and clobbered `OIDC_EXCHANGE_ERROR` into `RefreshAccessTokenError`, and the guard
  never fired. Making the error terminal in the callback fixed it. Beta-sensitive
  seams need a real round trip before the full wiring, so the verdict lands early.
- **Fail loudly at the wait, not at the far-downstream death.** The demo-reset web
  poll printed its success banner even on a 120s timeout, so a stalled production
  build looked like a clean reset until Playwright died opaquely much later. Moving
  the failure to the wait (non-zero exit plus a `docker compose logs web` dump)
  turns a confusing downstream symptom into an obvious local cause.
- **Changing a shared default in one task silently breaks another task's hardcoded
  fixture, and the final full-suite gate is where it surfaces.** T5 flipped the
  canonical Keycloak issuer to `http://localhost:8080/realms/shield`; T4's
  `test_oidc_exchange.py` had baked in the pre-T5 `keycloak:8080` issuer and leaned
  on the config default, so every happy-path case started failing with an issuer
  mismatch the catch-all message masked. The running system stayed correct
  throughout (T7's live `s26` exchange proved it end to end); only the unit fixture
  lagged. Fixing it was correcting a stale constant, not weakening a check. The
  lesson: when a task changes a default other tests read implicitly, re-run the full
  `-m unit` suite, not just the touched file, and the wrap-up exit run is the
  backstop that catches what per-task gates missed.

## Lessons learned (Sprint 8)

- **A flow that unit tests call green can be broken for every real user.** MFA
  sign-in passed `pytest -m unit` and a Sprint-7 vitest, yet the TOTP field never
  appeared in a browser. The cause sat three layers deep: `SignInForm` sent
  `totp: undefined`, next-auth serializes credentials through `URLSearchParams`,
  and `URLSearchParams` stringifies `undefined` to `"undefined"`, so the backend
  `!totp` guard saw a truthy value and verified a bogus code. The vitest could not
  catch it because it mocks `signIn()` and never runs the real serialization. Only
  a spec driving the actual browser through the real client library exposed it.
  That is the thesis of this sprint, proven the hard way.
- **Send the key only when you have a value.** The fix was one line,
  `...(totp ? { totp } : {})` in place of always passing `totp`. A default of
  `undefined` is not the absence of a field once it crosses a string-serializing
  boundary; the silent coercion made a broken auth path look like a routine
  bad-password rejection.
- **Idempotency belongs before the expensive side effect, not at the write.** The
  tech-debt extract guard had to sit before `extract_capabilities()`, not at the
  version-mint site, or a double-click would still fire the LLM call it was meant
  to prevent. Guarding at the cheapest correct point is the difference between a
  fix and a half-fix (Codex flagged exactly this in the plan review).
- **On an overload-prone box, the per-spec standalone run is the flake arbiter.**
  Full-suite e2e here repeatedly failed on cold-compile sign-in timeouts under
  load while every spec passed alone. A spec that dies at `auth.ts` sign-in under
  load is a documented load flake, never a logic bug; the authoritative full run
  is the quiet-box shutdown checkpoint.

## Lessons learned (Sprint 7)

- **"Feasible with curl" is not "works through the adapter."** T0's Vertex path
  was proven by a raw ADC `generateContent` curl, but the first live sweep (T1)
  still found two defects a keyless unit test could never hit: `google-auth`'s <!-- counted: historical -->
  token-refresh transport needs the `[requests]` extra (the unit test mocked
  `_bearer_token`, so it never exercised the real transport), and gemini-2.5
  "thinking" ate the output budget and truncated JSON. A real end-to-end sweep is
  the only thing that exercises the transport and the model's real output shape.
- **A silent "completed" on a truncated response is a lie.** `_parse_generate_content`
  returned a half-JSON draft as "completed" and it died downstream as an opaque
  `JSONDecodeError`. The fix is to fail LOUDLY at the seam: any non-`STOP`
  `finishReason` now raises and marks the `llm_call` failed with the real reason.
- **The token rides the header, not the URL.** The Vertex bearer token is sent as
  an `Authorization` header so an `HTTPStatusError` (which embeds only the request
  URL) cannot leak it into logs or `llm_calls.error_message` — mirroring the
  Gemini key-in-header lesson, and unit-locked.
- **Best-effort side effects must not roll back durable state.** A
  release-notification SMTP failure is logged loudly but the release still stands
  — the release is the source of truth. "Fail loudly" means surface the failure,
  not undo the thing the user already asked for.
- **A major auth dep bump is behavior-preservation work, not a feature.** The
  Auth.js v5 migration touched 34 call sites and re-wired the MFA signal (v5
  normalizes every credentials failure to `CredentialsSignin`, so the MFA branch
  surfaces via `signIn(...).code`, not `.error`). The bar was every auth e2e green
  and not one weakened test.
- **An allow-list built from "present" rows is an allow-list of everything, when
  every row is pre-seeded.** Risk synthesis guarded what the model could cite
  with three lists whose docstring said they held "codes the client's
  assessments never contained" — and they held every code that exists, because
  `provisioning.py` writes an answer row per catalog entry, `routes/attack.py`
  writes a coverage row per technique, and nothing under `apps/api/app` deletes
  one. They are now the codes each assessment SCORED (#403, PR #416). The
  transferable half is the SHAPE: where a table is pre-seeded, membership is not
  evidence of anything, and a guard keyed on membership is a guard keyed on
  nothing. Check what a row's EXISTENCE actually proves before filtering on it.
- **Narrowing a guard is half a fix; the other half is saying why the output got
  smaller.** Scoped allow-lists make technique and control links go sparse for
  any client whose assessments are largely unscored — which is correct and reads
  as a regression. Without a disclosure the change trades a silently wrong
  citation for a silently missing one, which is the worse of the two. The scored
  share is persisted at generate and read back by one parser that both the
  consultant's screen and the client's export call, so the two cannot disagree.
- **A disclosure field's NAME decides whether a gate can see it.**
  `check_disclosure_consumers.py` matches by PREFIX, so `citations_dropped` is
  invisible to it and `dropped_citations` is not (#373). The same field, the same
  reader, one green that means nothing and one that means something. Put the
  disposition first.

