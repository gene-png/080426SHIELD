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

The skip is keyed on AUTHOR; its justification is about CONTENT. A maintainer
can push commits to a Dependabot branch — the routine case is a bump that breaks
something and a human fixing it in place — and `pull_request.user.login` stays
`dependabot[bot]`. So the exemption would follow the BRANCH, and arbitrary
human-authored code would merge with the required audit check green and no audit
block anywhere. That is the class #93/#94/#95 record putting a client-facing
fabricated gap on `main`, arriving through the one PR class nobody can edit.

`check_bot_pr_is_manifest_only.py` runs only for the exempted author and fails
when that PR touches anything outside the manifest and lockfile set, naming the
paths. A human pushing code onto a bot branch is blocked instead of inheriting
an exemption written for a version bump.

Validated against all four open bot PRs — every one is manifests and lockfiles
only, so the allow-list matches what Dependabot actually writes here rather than
what its author guessed. The allow-list is deliberately **not** derived from
`.github/dependabot.yml`: that file names ecosystems and directories, not the
files an updater writes, so deriving it would encode Dependabot's internal
behaviour — a synchronisation with something this repo does not control.

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
