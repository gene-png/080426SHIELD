# 2026-09-22 — #254: the readers, not just the writer

_Landing entry for PR #461 (`fix/254-round5`), the follow-up to #444 and
#458. Moved out of `CONTEXT.md` under D-081: this is a dated event, not a
current-state description, and it is the third time this branch family has
hand-resolved a `CONTEXT.md` conflict whose only possible outcome was
keep-both._

**Landing with THIS PR (#461): the #254 follow-up.** Adversarial
review ran repeatedly on #444. The rounds that arrived before the merge
landed in the PR; a later round's findings reached the dispatching session
BEFORE the merge and were not incorporated into it, which is a different and
worse fact than the reviewer not having delivered. What that round found
includes the defect #254 exists to fix, surviving at the read end.

**Two corrections to the record of how #444 reached `main`**, because both were
wrong in my earlier account and this file is now the permanent version. Round 4
DID deliver: complete, with a terminator, to the dispatching session, before
the 18:40:55Z merge — not "never delivered", which names a different member of
`CLAUDE.md`'s absent / erroring / reported-to-nobody list. And Gene AUTHORISED
the merge; Dave performed it.

**A blank `legal_name` still printed a BLANK organisation line on the client's
DOCX/PDF/XLSX.** The five `*/exporters.py` and the admin fulfill path resolved
it with a bare `client_legal_name or "Client"`, and `"   "` is truthy, so it
never reached the fallback. They now call `app/client_naming.py`.

**That count was wrong twice, and the record says so rather than restating it.**
#458 fixed six readers under prose claiming "all six". A SEVENTH was found
afterwards in `routes/csf.py` — the CSF Playbook export, which feeds FIVE client
artifacts and lives in a ROUTE rather than in an `exporters.py`, so both the
sweep and the guard written to check it went past. An EIGHTH is in the web
layer, `lib/risk/client.ts`, under a comment claiming parity with the server
side that the same branch had made false. Both are fixed on
`fix/254-round5`. **This block still states counts, and that sentence used to
claim it did not** -- "no sentence here carries a count any more" sat above
"the five `*/exporters.py`", "#458 fixed six readers" and "feeds FIVE client
artifacts". A bare count invites a check; a count under a certification that
there are none ends it, over the exact class of number that went six to seven
to eight. The counts that describe a FIXED past event are kept because they
are what makes the sequence legible; what is gone is any claim that a current
population has been fully enumerated.

**Migration 0050's predicate was rewritten from SQL to Python.** Its first
version was `trim(legal_name) = ''`, and single-argument `trim()` is
SPACE-ONLY on both engines — measured: tab, newline and NBSP all survived it,
while `str.strip()` (what the reader uses) treats all four as blank. NBSP is
the one that actually arrives, since it is what PDF and Word extraction emit.
The normalisation now runs in Python so the migration and `is_named_org` share
`str.strip()` itself rather than two descriptions of it, and 0050 now runs
against DATA — a row per whitespace class, plus a derived sweep over the whole
Unicode whitespace set.

**A regression test I wrote could not fail.** `test_engagement_refuses_a_legacy_blank_name_with_422_not_500`
posted `csf_profile: "current"`, which is not a `CsfProfile` member, so Pydantic
422'd the body before the guard ran and the status-only assertion passed for the
wrong reason. Measured: with the guard reverted it still passed, exit 0. It now
sends `MOD` and asserts the typed `reason` (`organization_not_named`) rather
than a status code or a sentence, and goes red on that same revert. The guard
was given a typed detail so there was something to assert; the other
bare-string 422s in that module are tracked in #453.

Also: `hasIntakeData` gained the four `primary_contact_*` fields (Step 3 writes
them one per blur, and the pill said "No intake started" over them) and is now
genuinely derived from one `cardRows` array the card renders; the provisioning
ratchet tests `title` the same way it tests `org_name`; and two comments that
published a grep as the authoritative writer set are back to being lists that
say they are lists — that grep returned ZERO hits in `routes/intake.py`, the
main user-input writer, which goes through `setattr`.

**#254 fixed and ON `main` at `d5f97eb` — a self-serve client's email was its
organisation's legal name.** (This paragraph arrived saying "landing with THIS
PR, not yet on `main`", which was true while #444 was open and false the moment
it merged. Corrected here because this PR is resolving a conflict in the same
paragraph and leaving a known-false claim beside the resolution is worse than
the small scope increase.) `"(pending intake)"` was the codebase's
marker for "nobody has named this client yet", READ in 17 production sites (13
in `apps/api/app`, 4 in `apps/web`) and **written in none** — the only
assignments were four unit-test fixtures.
<!-- counted: grep -rn '"(pending intake)"' apps/api/app apps/web/src -> 19 hits, 17 live conditionals + 2 comments; grep -rn 'legal_name\s*=' apps/api/app --include=*.py | grep -v '==' for the writes, at 3c2dd0a, 2026-09-22 --> So every one of those guards was dead,
and what reached the organisation line of a client deliverable was whatever
`routes/auth.py` derived from the registrant's email: the domain for an unknown
company domain, and **the registrant's own display name** for a personal mailbox
— a private individual's name, as the client organisation, on a delivered
document.

**`Client.legal_name` is now nullable and NULL means nobody has named the org**
(D-080, migration 0049). Both write paths in `routes/auth.py` are fixed. The
sentinel is deleted from the API entirely; it survives only as web COPY in
`apps/web/src/lib/org-name.ts`, which nothing branches on. Ten of the thirteen
API guards collapsed to a plain read of the column.

`routes/admin.py`'s create-client write is a **stated exemption** — an admin
typing a name is a human naming an org — and the reason the guards key on the
NAME being absent rather than on `intake_completed_at`: an admin-created tenant
has a real name and never completes intake, so an intake-keyed guard would blank
its deliverables and refuse its engagements.

Migration 0049 backfills only rows that reconstruct exactly what the two
self-serve paths wrote. Measured against the dev Postgres before applying: 4
client rows, 1 matching, 0 matching the display-name predicate — and the one
match is a live instance of the defect.
<!-- counted: docker compose exec -T db psql -U shield -d shield -At, the four SELECT count(*) statements written out in alembic/versions/0049's MEASURED block, 2026-09-22 -->

**#236 and #389 fixed: two client-reaching surfaces that failed silently.**

**#236** — `app/home/page.tsx` fetched four endpoints in one `Promise.all` with
no `catch`, and there is no `error.tsx` anywhere under `apps/web/src/app`, so
any one rejection took the whole page down — including the client's released
reports, which have nothing to do with the endpoint that failed. Now
`Promise.allSettled`, with each failure recorded per panel.

**The half that was the actual work**, and why the site comment said this was
"considered and left": `allSettled` alone is not the fix. Passing `[]` / `0` /
`null` for a panel that ERRORED makes the page assert "you have no
engagements", "no unread messages" — claims about the client's account made
from a failure. `HomeDashboard` now takes `unavailable: HomePanel[]` and
renders "could not be loaded" for those, so a degraded panel is distinguishable
from an empty one.

**#389** — `SignUpForm`'s `await res.json()` was unguarded inside the typed-422
branch, so a non-JSON body (proxy HTML, empty 429, gateway timeout) rejected the
submit handler and `setPending(false)` never ran: the Create account button
stayed disabled forever with nothing on screen, on the **public** sign-up page.
Now parsed inside a `try`, falling through to the existing plain-language copy.

Both verified RED-ON-REVERT individually. Web gates from the worktree:
`tsc` 0 errors, `eslint` clean, `vitest` 694 passed.

**#371 fixed: the client is no longer told the value was restored when it was
not.** `describeSaveError` printed "The value on screen has been restored to
what the server has" unconditionally, and both self-assessment surfaces called
it BEFORE the re-fetch that does the restoring. When that re-fetch also failed,
the client sat looking at the refused value under a sentence saying it had been
replaced by server truth — and the `catch` block's own comment claimed the
message was "the honest one: we cannot show what the server has", which is the
opposite of what the message said.

The restoration clause is now opt-in. Callers show the bare failure message
immediately — nobody should wait on a re-fetch to learn their edit failed — and
replace it with `{ restored: true }` only once the re-fetch resolves, so each
sentence is true at the moment it is on screen.

`CLAUDE.md`: a success record must be written where the success is, not before
it. Recorded after N-019, #47 and W1's accounting log — the list is the count,
and this one is the first where the false record is read by a CLIENT rather
than by a developer.

**The deferral reason had expired:** the issue was filed rather than fixed
because `describe-save-error.ts` had two open PRs against it (#362, #366).
Both merged, so it was unblocked.

