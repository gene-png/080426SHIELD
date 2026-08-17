# Gene — current status

_Owner: Gene (gene-png). Only Gene's sessions write this file._
_Last updated: 2026-08-17 (W1 CSF merged as PR #54; nothing on a branch)_

Keep this short and current: your sessions overwrite it freely (it's yours
alone, so it never merge-conflicts). Dave's agents read it at `/pickup` to
know what you have in flight without digging through branches.

## Branch / in flight

**Nothing.** `main` is at `61d90e3` (PR #54, W1's CSF step), CI green on all
five checks.

State of `main` — the stretch, what landed, the open follow-ups and the lessons
— is in **`CONTEXT.md`** now, not here. This file is in-flight only.

## Pick up here — W1's ZT step

Order is **CSF → ZT → Risk → ATT&CK**; ATT&CK stays gated on W2. Issue **#44**
has the settled design, **D-045** has the CSF implementation and its four audit
rounds. Read D-045 before starting ZT — the ZT step is the same shape, and the
four rounds are the map of where it goes wrong.

Two things to carry into ZT specifically:

1. **Budget four audit rounds.** CSF took four, and the defect rate did not fall
   across them — because round 4 caught a regression introduced by round 3's own
   fix. That is the audit working on itself, not the work failing to converge.
   Do not read a clean round 2 as a reason to stop.
2. **Watch one specific shape.** A guard added to stop OVERCOUNTING has twice
   created a path where nothing was recorded at all — `if not fields and not
   unknown_fields` in round 1, `if recognized_values:` in round 3. Both times:
   a conditional meant to prevent double-counting whose false branch silently
   drops the record instead of emitting it under a different reason. When ZT
   needs one, make the false branch emit something; a zero-value record naming
   the fault is honest, silence never is. (Also now a rule in `CLAUDE.md`.)

**ZT owes one thing CSF did not:** `zt.py` logs `value=repr(raw)[:120]`, which
is AI output in a log line and violates #44's constraint 1 (audit rows and logs
get reason codes and counts ONLY). That is mine, it predates the rule being
stated, and W1's ZT step is where it gets fixed.

## Open decisions — NOT to be reconstructed from memory

Both are written out in `CONTEXT.md` under the cross-service section: **W0's
freeze** (due after Part 3 reopen is scoped for CSF; the "#37" reference in older
handoffs is wrong — #37 is closed and is a different issue) and **W3 gating W2**.

## Environment — needs a human

- **The root `.env` is in live mode with a key that returns 401.** Every AI call
  502s. It was flipped to fixture for #54's gate run and restored to
  `SHIELD_LLM_MODE=live` exactly as found; the key still needs replacing.
- **The `api` container is currently running FIXTURE mode**, left that way after
  the gate run because restoring live would restore the 401.
  `docker compose up -d --force-recreate api` puts it back.
- Once there is a working key, **#51 is the live run W1 actually owes** — nothing
  in the CSF accounting has ever been seen against a real model, and fixture mode
  structurally cannot produce a drop.

## Do not merge

**PR #29** — green in CI, gated on the W2 resolver rewrite plus a clean
adversarial audit. It is the thing most likely to look mergeable after a break.
