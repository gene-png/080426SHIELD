# 2026-09-24: tiers measure consequence on the delivery path; the format step reads prettier's version

Branch `docs/tier-rule-and-prettier-derivation`, base `5783fae` (#527 merged).
Decision: D-087.

## What changed

- **CLAUDE.md's tier paragraph.** The tier-3 definition itself now states the
  consequence test: wrongness that changes nothing about what the client ends
  up with. A consultant acting on a false screen is on the delivery path, and a
  reviewer or developer misled by a false gate is not. It names the class "a
  label's name is not its test", and points at #528 for the missing compliance
  term. D-087 carries the #70/#74 reasoning, including the exporter measurement
  that argues the other way.
- **The MANDATORY format step** reads prettier's version with
  `scripts/prettier-hook.sh --print-version`, the hook's root-importer reader,
  which refuses when it cannot read. It is Git Bash only, and says so. It used
  to say 3.9.6 while the lockfile said 3.9.8.
- **The same stale pin, at every site that tells someone what to do:**
  - both dev agents' Step 0 guard, re-keyed and given its own cause (the agent
    layer IS present, and the branch is behind `main`);
  - both dev agents' Gates blocks;
  - `README.md`, `ONBOARDING.md` (the command, and "replace gate 3's hardcoded
    prettier" when copying a staged queue), `docs/development.md`;
  - `BUILD_REPORT.md`'s "Repo format" row, `CONTEXT.md`'s queue-gate note, and
    `context/gene.md`'s standing gate list.

  **Swept by the literal `3.9.6`, not by the subject**, which is how the first
  pass missed four of these; review found them. What still says `3.9.6` is a
  record, not an instruction, and is left as written. That is the staged
  sprint-queue JSONs (closed sprints' plans of record), the dated
  measurements in `context/gene.md` and `DELIVERY_PLAN.md`, and
  `tests/gates/prettier_hook.sh`'s fixtures, which are test data. The rationale in `scripts/prettier-hook.sh`
  and `.pre-commit-config.yaml` is now dated (2026-08-30).
- **D-086's rationale is corrected by D-087**, not edited: `mvp-blocking` is
  board membership. The gate's docstring and a test comment are corrected in
  place.
- **To pay for the new clauses**, the over-match and corpus rules' instances
  moved to D-087 per the size ratchet's cut list. Their instructions stay,
  including "say which one a fix is".

## Measured

- **The format command, both directions (Git Bash):** it read 3.9.8 and the
  full-repo `--check` exited 0. In a repository with no lockfile, the hook
  refused, `${v:?}` exited 1, and `npx` never ran.
  `tests/gates/prettier_hook.sh` passes, including "lower and transitive
  entries ignored".
- **The re-keyed agent guard, in both states:** silent on this branch's
  CLAUDE.md, and HALT on `main`'s.
- **CLAUDE.md is under the size gate**, and the canary is the last line.
- **Review of the first draft found:**
  - its node regex took the lowest prettier in the lockfile (#311);
  - the agents' guard would have halted every dispatch;
  - the in-container rejection had the wrong reason. The web container never
    mounts `.prettierignore`, and it cannot see most of the repo.

  All three are fixed here.
