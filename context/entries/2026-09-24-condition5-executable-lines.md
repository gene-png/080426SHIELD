# 2026-09-24: condition 5 ignores a diff that changes nothing that runs

Branch `track1/cond5-executable-lines`, base `f17cc5a`.

## Why

#530's whole `docker-compose.yml` diff was comments, and it still came back to
the owner under condition 5. The owner's rule: a diff that changes no
EXECUTABLE line in a condition-5 path does not trip condition 5. Comments,
docstrings and landing entries cannot alter behaviour, so the exception is
mechanical and can be computed. The status-based narrowing measured earlier
could not be.

## What changed

- **`check_condition5.py`**, a new gate.
  - **The path list** is the indented list under `### Condition 5: the paths`
    in CLAUDE.md, which the bullets explain.
  - **Prose is not read.** The first draft read the bullets' backticked
    tokens, and the bullets name paths they EXCLUDE (`apps/web/**`,
    `alembic/`), so every web change would have tripped.
  - **What counts as executable, per file type:**
    - Python: the AST with docstrings removed; a tool-directive comment
      (`noqa`, `nosec`, `test-integrity:`, …) counts.
    - YAML and JSON: the parsed object.
    - Shell: code lines; every line counts if the file has a heredoc.
    - Data, docs, and anything under `gates/` or `fixtures/`: every line.
    - Anything else (TypeScript, binaries): unclassifiable, exit 2, read as
      tripped.
- **`audit-gate.yml`** runs it with `--report`, a step inside the merge-rule
  job. It prints the verdict to the job summary and exits 0 whether or not
  condition 5 trips, because tripping is routing, not a defect. It exits 2
  only when it could not look. There is no pipe into `tee`, which would lose
  the 2 (#213).
- **CLAUDE.md**:
  - condition 5 states the exception;
  - the section carries the list;
  - the measurement table has a column for the new rule;
  - the `_HSPACE` bullet shrinks to its rule plus a D-058 pointer, which pays
    for the additions under the size gate.

## The measurement, against both recorded windows

The windows are the 15 most recent PR merges at each date. For 08-26 that is
at `fdfde7d^1`, the commit before D-059 landed; for 09-21 it is at `897eeae`,
with the selector CLAUDE.md records. Each window is scored under condition 5
as it stood that day.

| window | old rule | new rule | newly cleared |
| --- | --- | --- | --- |
| 2026-08-26 | 4 cleared / 11 back | 4 / 11 | none |
| 2026-09-21 | 2 cleared / 13 back | 4 / 11 | `b516891` (compose comments only), `7c2802c` (an `ai/engine.py` docstring only) |

**The old-rule column reproduces both recorded figures exactly**: 4/11 and
2/13. That reproduction is what licenses the new column. The first attempt at
09-21 gave 3/12, because it left out the compose files; they entered condition
5 in `b516891` itself, on 2026-09-19. Both newly cleared diffs were read by
eye: comments only, and a docstring only.

## Proof

- **Fixtures:** 10 cases, including adversarial ones (a `# nosec` edit, a
  heredoc `#` line, a fixture comment, a TypeScript comment, an empty diff).
  `check_gate_fixtures` passes: 72 cases across 12 gates.
- **Red-on-revert:** removing the directive check, the heredoc rule or the
  fixtures-are-data rule turns its named unit test red.
- **The list and the prose agree:** a unit test pins that every listed path is
  named in the bullets.

## Limits

- It does not re-derive the "does any workflow execute it" set. That stays
  self-attested, as the withdrawn derivation in
  `check_merge_rule_conditions.py` explains.
- A live prompt outside the listed paths still needs a diff read.
- TypeScript and JavaScript are always unclassifiable until there is a lexer.
- CLAUDE.md is left with 23 bytes of headroom under its size gate.
