# Auto-merge guard probe (2026-10-16)

A throwaway PR, opened by the coordinator (advisor ruling #736 6207756046 item 1) to test one thing: whether `gh pr merge --auto --match-head-commit <A>` refuses to merge after a later commit B is pushed. This PR is meant to be closed unmerged. If this file is on `main`, the guard did NOT hold, and the merge-rule PR must not rely on `--auto` until that is fixed.
