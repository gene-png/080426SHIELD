# Gene's Context — 080426SHIELD

**Last updated:** 2026-08-20 (the in-flight-assessment fail-open question is answered: the migration's own docstring originally said NULL means "leave scoring exactly as it does today" — the same silently-reads-as-confirmed shape D-054 already rejected once, now caught a second time, this time in draft text before it shipped; blast radius checked before deciding — zero RELEASED ATT&CK assessments, no production deployment yet, all 30,384 rows are dev/demo across 16 draft/14 approved/18 discarded — so fail-closed costs nothing real; three-value semantics adopted (NULL=never resolved→pending, []=resolved clean→normal, uncleared inferred→pending); sizing corrected to 2-3 sessions / 4-5 adversarial rounds per the W1-ZT precedent, with a stated principle worth keeping — "a rule rewritten three times is a design problem, enumerate the state space before patching further"; analytics half done, 10 tests green; #104 nearly through CI, only E2E left as of this check)

This file is owner-write-only. It exists so any session (mine or a relay) can pick up the real state of the project without reconstructing it from scattered chat history. Update it after every substantive decision. **This file lives in the repo, not on any one machine — a local computer restart does not affect it.**

## Branch / in flight

`main` has #78, #80, #76, #49, #50, #81, #82, #86, #88, #91, #93, #94, #95, #96, #97, #98, #100, #103 merged, all verified directly on GitHub. Open: #104 (docs-only closing-keyword rule; Python and Demo and Web and Secret-scan and the audit gate all green, only E2E still running as of this check) and #29 (still not closed as superseded despite D-054 saying it would be once W2 lands — flagged twice now, still open). #84, #85, #87, #89, #90, #92, #102 filed and open. #101 reopened, correctly not yet re-closed (no PR exists for the persistence work yet — it's still on a branch). #99 closed as superseded.

## #101/#102 persistence work — in progress, no PR yet

**The fail-open catch was in the other session's own draft text, and they owned it directly.** The migration docstring itself originally read "NULL means leave such a technique scoring exactly as it does today" — which is precisely "silently reads as confirmed because nothing on record contradicts it," the same shape D-054 already rejected on the nullable-vendor default. This is the second time this exact principle has had to be re-derived from scratch rather than existing as a standing rule; worth writing it down somewhere durable (CLAUDE.md, the way #104 did for the closing-keyword footgun) so a third instance doesn't require rediscovering it again.

Blast radius was checked before deciding, not assumed: zero RELEASED ATT&CK assessments exist, there is no production deployment yet, and all 30,384 current rows are dev/demo data (16 draft, 14 approved, 18 discarded). This is new, useful information — the whole system has not yet been used on a real client engagement, which is exactly why this round of pre-launch bug-hunting is cheap: nothing delivered gets retroactively changed by tightening the default now. I cannot independently verify these row counts myself (no database access, GitHub only) — they need to land in the migration docstring or PR body where they're citable later, per the other session's own stated plan, not just asserted in a relay.

Decision: three-value semantics. NULL (citations never resolved, predates the resolver) scores pending. `[]` (resolved, nothing needed inferring) scores normally. A non-empty, uncleared inferred list scores pending. `seed_demo.py` will write `[]` explicitly rather than rely on a default, so seeded data is confirmed by a deliberate, single-place assertion instead of every pre-migration row being grandfathered by a default nobody chose.

**Sizing corrected**, and this is the strongest part of this round: cited W1-ZT's own five-adversarial-round precedent from DELIVERY_PLAN and pulled the general principle out of it — "a rule you have rewritten three times is a design problem, not a bug list; enumerate the state space instead of patching the case in front of you." pending_review's real input space is status × flag-state × cleared-state × NULL-vs-empty, and the plan is to write that truth table before writing more logic, not after. Re-sized to 2-3 sessions / 4-5 adversarial rounds, to be recorded in DELIVERY_PLAN when the PR opens. This is exactly right and worth treating as a standing practice, not a one-off correction.

Progress as of this entry: analytics half done, 10 tests green on the four 5.1 invariants, pending_review as its own field, excluded from "addressable" rather than scored as a zero. That last distinction — what the addressable-coverage metric actually is, and whether it's client-facing — isn't something logged elsewhere yet; needs to be stated explicitly in the PR the same way the panel-copy string is being pinned, not left implicit. Next: persistence wiring into run-AI, then the seed, then the panel-copy flip.

## D-054, PR #96, PR #97, PR #98 — recap, see prior entries for full detail

D-054: W2 cut fresh off main, #29 never merges, closed as superseded once W2 lands (still not done — flagged three rounds running now). Nullable-vendor default set to refuse-and-flag — the same principle just reapplied to the #101/#102 NULL-citation case above. PR #96/#97/#98 recap unchanged from prior entries; branch protection now enforces the audit gate for real.

## MVP tracking — status this round

Item 5 (W2) DONE. Items 3a and 4 DONE. Item 3b's persistence sub-work (#101/#102) is in progress, correctly re-sized to 2-3 sessions / 4-5 rounds rather than treated as #103-sized. Items 6, 7, 8 not started. New context worth keeping: zero RELEASED assessments and no production deployment yet — the whole MVP effort is still pre-launch, which is the frame the "shipped falsehoods to a consultant" language in earlier entries should be read against: forward-looking risk being closed before go-live, not a live incident.

## Open decisions — NOT to be reconstructed from memory

Whether to write the "missing data defaults to unconfirmed, not confirmed" principle into CLAUDE.md now that it's recurred twice (nullable-vendor, NULL-citation) — not yet done, worth doing before a third instance. What "addressable" coverage actually means and whether #102's exclusion of pending_review from it is client-facing — not yet stated anywhere, needs to land in the upcoming PR. #29 still not closed as superseded — third round flagging this. `Require a pull request before merging` still off on branch protection. Local-device mirror of this file — still unconfirmed whether Gene wants ongoing sync. #90's build, #89's pin test, #92's contract-test fix — still not built. #57, ServiceStatus.RELEASED (#62), W0's freeze shape — unchanged. Whether to parallelize item 6 — still undecided.

## Resolved as of this round

The in-flight-assessment fail-open question I raised is answered: three-value semantics adopted, NULL and uncleared both score pending, blast radius checked (zero RELEASED, all dev/demo) before deciding rather than assumed. Sizing corrected to 2-3 sessions / 4-5 rounds with a generalizable principle stated for why. #104 confirmed nearly through CI (only E2E outstanding at last check).

## Session length — measured from git history (unchanged, see prior entries)

Still roughly 4 to 8 hours per session. Item 3b's #101/#102 sub-work is now explicitly sized at 2-3 sessions on its own, per the correction above — folded into future revisions of this figure once it actually lands.

## Environment notes (standing)

Unchanged from prior entries: Postgres migrations clean through 0043, applied to dev Postgres and verified via alembic current. Provider live key: RESOLVED, reverted to fixture-by-default on purpose. New this round: zero RELEASED ATT&CK assessments exist and there is no production deployment yet — worth keeping as standing context for how "client-facing" language elsewhere in this file should be read.

## Do not merge

PR #29 — under D-054 this should be closed as superseded now that W2 has landed; confirmed NOT yet closed, three rounds running. Reference material only; still open on GitHub.

## Recurring defect shapes to watch for (CLAUDE.md)

A test that supplies its own expected value or precondition from the thing under test cannot fail — 12 confirmed instances, unchanged this round. Missing/absent data silently defaulting to the confirmed or safe-looking state instead of the unconfirmed one — now two real instances (D-054's nullable-vendor default, and this round's NULL-citation migration text), both caught before shipping rather than after; worth a standing CLAUDE.md line rather than a third rediscovery. A rule rewritten three times without its input space ever being enumerated is a design problem, not a bug list — new this round, stated as a general principle rather than just applied once; the fix is writing the truth table before the next patch, not after. A mechanism built to enforce a format only proves it handles the formats it was tested against — two instances (#98, #103), both closed correctly. Code can assert the opposite of what actually happens and nothing catches it until a human or an adversarial pass reads the code path directly — #103's panel-copy inversion remains the clearest instance; #102's panel-copy flip is this same shape being caught proactively. An issue tracker's own auto-close mechanism can produce a wrong status line without any code being wrong — #101, documented in CLAUDE.md via #104. A status line that is wrong is worse than none — three vectors logged: a hand-maintained plan doc, a CI gate's self-description, an issue tracker's auto-close. A migration's effect on existing rows is not uniform by default — this round's NULL-citation decision is the resolved instance of exactly this pattern. A mechanism that reports on a violation is not the same as a mechanism that blocks it — closed for the audit gate specifically. Credential material never travels through a relay conversation, even when explicitly offered. Test behavior changes get called out explicitly in the test itself, never silently adjusted. A rule whose measured signal is a small fraction of its raw output should be narrowed rather than kept broad and ignored. A mutation-testing survivor is only meaningful relative to which tests were actually run against it.
