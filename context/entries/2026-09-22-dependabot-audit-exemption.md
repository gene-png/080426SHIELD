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

## Human review is UNCHANGED

This removes the audit-block requirement, not review. A Dependabot PR still
needs `gh pr review --approve` from a named human — which is branch protection
rather than this gate, and which is attributable through the API in a way a line
of body text never was. The audit block exists so an adversarial reviewer's
findings are recorded; there are no findings to record about a lockfile bump,
and a block written to satisfy the matcher is the decorative-marker defect.

## LATENT, not fixed

**Zero Dependabot PRs were open when this landed.** Nothing was unblocked and
nothing visibly changed, which is exactly why it needed tests rather than a
manual check: an empty queue is not an exemption, and nobody would notice the
operator flipping until a bot PR arrived and the gate silently stopped applying
to everyone else.

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
