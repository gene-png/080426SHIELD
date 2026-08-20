## D-054 — The §14 audit gate is a merge check, not a line in a document

**Date:** 2026-08-20 · **PRs:** #98 (the gate), #96 + #97 (the defects that motivated it) · **Supersedes the deferral reasoning in D-051**

Plan §14 — "every workstream merges on a clean adversarial-reviewer audit, not
on a green suite" — was skipped on three consecutive code PRs (#93, #94, #95).
All three were green. All three put a defect on `main` that a retro-audit then
found, including a client-facing fabricated gap (#96).

**Two causes, and only one of them was mine to forget.** The gate lived in
exactly one place, `docs/plans/2026-08-08-cross-service-integrity.md:580`, which
is not auto-loaded; `CLAUDE.md`, which is, had no mention of it. And the agent
resolved a conflict between "do not invoke subagents unprompted" and §14
silently, in favour of not running it, instead of raising it.

**The first proposed fix was to document the gate in `CLAUDE.md`. Rejected by
Gene, correctly.** That is a discipline fix, and discipline against this exact
shape has failed nine recorded times (#72) — including instances written minutes
after the rule was logged. Visibility was never the binding constraint.

**The decision: a deterministic merge check** (`scripts/check_audit_evidence.py`,
`.github/workflows/audit-gate.yml`). A PR touching code fails unless its body
records an `## Adversarial audit` section with `Findings:` and `Disposition:`
lines. Stdlib-only, sub-second, no model in the loop — it costs none of what W8b
was rightly deferred for, and it is not a substitute for W8b either.

**What it proves is narrow and stated as such:** that an audit was RECORDED, not
that it happened or was any good. Same honesty convention as `SMOKE_TEST.md`.
What changes is that skipping becomes deliberate and visible instead of silent,
and all three misses were silent.

**It is not enforcing yet, and that is the load-bearing caveat.** A workflow job
only reports. It blocks only once "Adversarial audit recorded" is a required
status check in `main`'s branch protection — and as of 2026-08-20 `main` has NO
branch protection rules at all, not even force-push blocking. Until that is
configured the gate is a visible red X and nothing more. Recorded here because
the first version of the gate's own docstring claimed it "blocks the merge",
which was false and was the #72 pattern one level up.

**Its own adversarial audit found eight defects in it**, all fixed before merge —
including `main()` having zero test coverage (inverting its exit code left the
suite green), `edited` missing from the workflow triggers (so a fixed PR stayed
red with no way to clear it), and `**Findings:**` in this repo's own prose style
being rejected. The gate caught its own defects only because it was audited; it
would not have caught them itself.
