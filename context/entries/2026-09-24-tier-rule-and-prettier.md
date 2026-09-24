# 2026-09-24: tiers measure consequence on the delivery path; the format step reads prettier's version

Branch `docs/tier-rule-and-prettier-derivation`, base `5783fae` (#527 merged).
Decision: D-087.

## What changed

- **CLAUDE.md's tier paragraph** now says the test is consequence, not
  audience: tier-3 means the falsehood changes nothing about what the client
  ends up with. A consultant acting on a false screen is on the delivery path;
  a reviewer or developer misled by a false gate is not. It also names the
  class: a label's name is not its test. The #70/#74 reasoning, including the
  exporter measurement that argues the other way, is in D-087.
- **CLAUDE.md's MANDATORY format step** reads prettier's version from
  `pnpm-lock.yaml` at run time. It said 3.9.6 while the lockfile said 3.9.8.
  The command was run in Git Bash and PowerShell 5.1, in both directions.
- **D-086's rationale is corrected by D-087**, not edited. `mvp-blocking` is
  board membership, not "blocks the MVP". The gate's docstring and a test
  comment are corrected in place.
- **To pay for the new clause**, the over-match rule's `2nd Floor` narrative
  moved to D-087, per the size ratchet's prepared cut list.

## Measured

- CLAUDE.md is under the size gate, and the canary is the last line.
- An in-container `pnpm format:check` was rejected as the derived form. It
  flagged 177 files on a working tree, all gitignored build output plus
  `pnpm-lock.yaml`, which CI's clean checkout never has.
- A backspace byte reached `DECISIONS.md` through a heredoc and was caught by
  reading the bytes back. It was fixed with `chr(92)`, and
  `check_no_control_chars` is clean.
