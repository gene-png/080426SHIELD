# 2026-09-25: the enforce_admins sweep (#595)

Branch `track1/enforce-admins-sweep`, branch-start base `2028f38`.

## Measured

2026-09-25T14:55Z, `gh api repos/gene-png/080426SHIELD/branches/main/protection`:
`enforce_admins` true; a pull-request review block present with 0 approvals
required; `strict` true; seven required contexts. The owner turned
`enforce_admins` on this week.

## The sweep

Grepped by shape rather than by one literal: `enforce_admins`, "merge past",
"past a red", "are admins", "non-admin", "bypass" near a check or protection.
`DECISIONS.md` and dated `context/` entries are history and are left alone.
For each present-tense site, the second question: does its reasoning still
hold now that admins cannot bypass?

- **`CLAUDE.md`, the reviewer rule.** The claim that the authorisation is prose
  nothing checks STILL HOLDS: the audit gate reads only that the lines exist.
  The example given for it (admins merge past a red gate) no longer does, and
  is date-qualified.
- **`docs/security.md`.** Restated with the command, the date and what it
  means.
- **`DELIVERY_PLAN.md`, the branch-protection section.** The earlier bullets
  are kept as a dated record under a re-measurement. "A pull request is not
  required" is now doubtful, and the "guardrail, not a wall" conclusion
  depends on it: see #596.
- **`DELIVERY_PLAN.md`, the §14 note.** "Binds a non-admin ... and nothing
  else" is date-qualified.
- **`audit-gate.yml`, the Dependabot exemption.** The 2026-09-22 measurement
  stays; the re-measurement is added. The reasoning HOLDS: the skip removes a
  check, it makes nothing red, so it works the same whoever merges. "Merge
  past a red required check" now first means switching the setting off.
- **`check_bot_pr_is_manifest_only.py`.** The threat model HOLDS, and never
  rested on admins: a bot-authored PR rewriting the audit gate goes through
  GREEN checks, so there is nothing for an admin to bypass. The clause is
  date-qualified and says so; the test docstring matches.
- **Left as written, and why:** `check_recalled_counts.py` and the Dependabot
  test's module docstring say "merging past a red check" is the only way out;
  that is now harder, not easier, so the reasoning is stronger. The
  Dependabot test's 2026-09-22 comment and a fixture incident are dated
  records. `check_audit_evidence.py`'s docstring is corrected in #591, and is
  not touched here to keep the two PRs apart.

## Found, not fixed here

With `enforce_admins` on and a review block present, a direct push to `main`
is probably refused for everyone. If so, CLAUDE.md's direct-to-`main`
exceptions describe a push GitHub will reject. Filed as #596 for the owner:
derived from the API, not tested by pushing.
