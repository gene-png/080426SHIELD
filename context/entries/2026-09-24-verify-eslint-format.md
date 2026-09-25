# 2026-09-24: worktree ESLint verification runs again

Branch `track1/verify-eslint-format`, base `20f747f`. Reported by track 2.

`scripts/verify-in-worktree.sh eslint` passed `--format unix`. ESLint 9 (the
repo pins 9.39.5) removed that formatter from core, so every run exited 2 with
"The unix formatter is no longer part of core ESLint". It then printed that it
had run "the same invocation `pnpm -F web lint` uses", so the web-lint half of
worktree verification checked nothing on every branch since the flag arrived
(`0519df7`, 2026-09-10).

The fix drops the flag. The printed line is now built from the command that
ran, so the message and the invocation cannot disagree.

| run | before | after |
| --- | --- | --- |
| clean tree | exit 2 | exit 0 (3 warnings, as the script's own comment records for `eslint .`) |
| planted parse error | exit 2 | **exit 1** (`Parsing error: Expression expected`) |
