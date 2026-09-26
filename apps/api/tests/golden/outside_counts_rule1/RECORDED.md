# Recorded once, never regenerated

These files are the DOCX, PDF and XLSX that `main` rendered for a rule-1 (approved
before #620) ATT&CK assessment **before #621**. They pin option (a): #621's
counts and columns appear only under D-094's rules, and an assessment approved
before #620 renders what was delivered.

- **Recorded from:** `main` at `22c47a4` (#657), which contains #620 and not #621.
- **Recorded on:** 2026-09-26, in a `--rm` `shield-v2-api` container mounting a
  detached worktree at that commit.
- **How:** `record()` in `tests/unit/test_attack_outside_counts_follow_the_rule_set.py`,
  copied into that worktree and called with this directory. `world(1)` builds the
  world. It uses only the four legacy statuses, one pending claim and unscored
  techniques, which is what a rule-1 assessment can hold.

Do not regenerate these to make a test pass. A difference is the defect.
