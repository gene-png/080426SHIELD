#!/usr/bin/env bash
# Secret-scan a merge-queue group: the commits the queue added on top of main.
#
# WHY THIS EXISTS: gitleaks/gitleaks-action@v3 refuses the merge_group event.
# Its src/index.js lists supportedEvents = push, pull_request, workflow_dispatch,
# schedule, and exits 1 with "The [merge_group] event is not yet supported" for
# anything else -- so "Secret scan (gitleaks)", a required check, would be red on
# every queue entry. On merge_group only, ci.yml runs the same gitleaks version
# the action defaults to (8.24.3), checksum-verified, through this script.
# REMOVE IT when the action supports merge_group: re-read supportedEvents in the
# action's index.js at the tag ci.yml pins.
#
# Usage: gitleaks-merge-group.sh <gitleaks-binary> <base-sha> <head-sha>
#
# Exit codes (D-090): 0 scanned, no leaks; 1 gitleaks found a leak (its own
# non-zero); 2 could not look -- bad arguments, an unknown sha, or a range with
# NO commits to scan.
#
# THE ZERO-COMMIT GUARD. The range uses the action's own log options,
# `--no-merges --first-parent`. If the queue builds a MERGE commit rather than a
# squash (the queue's merge method is configured separately from the repo's),
# the group's only first-parent commit is that merge, `--no-merges` drops it, and
# gitleaks would scan nothing and report clean. A scan of zero commits must
# never pass, so the count is taken first and zero is exit 2.
set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "gitleaks-merge-group: could not look -- usage: $0 <gitleaks> <base-sha> <head-sha>" >&2
  exit 2
fi
gitleaks=$1
base=$2
head=$3

for sha in "$base" "$head"; do
  if ! git cat-file -e "${sha}^{commit}" 2>/dev/null; then
    echo "gitleaks-merge-group: could not look -- ${sha} is not a commit in this checkout" >&2
    exit 2
  fi
done

range="${base}..${head}"
count=$(git rev-list --count --no-merges --first-parent "$range")
if [ "$count" -eq 0 ]; then
  echo "gitleaks-merge-group: could not look -- ${range} holds no non-merge first-parent" >&2
  echo "commits, so gitleaks would scan nothing and report clean. If the merge queue" >&2
  echo "builds merge commits, this scan's range must change before it can pass." >&2
  exit 2
fi

echo "gitleaks-merge-group: scanning ${count} commit(s) in ${range}"
set +e
"$gitleaks" detect --redact -v --log-opts="--no-merges --first-parent ${range}"
status=$?
set -e
if [ "$status" -ne 0 ]; then
  echo "gitleaks-merge-group: gitleaks exited ${status}" >&2
  exit 1
fi
echo "gitleaks-merge-group: no leaks in ${count} commit(s)"
