#!/usr/bin/env bash
#
# Launch the full-engagement observation run and preserve everything it emits.
#
# WHY THIS EXISTS, rather than the spec doing it all itself: Playwright writes
# `trace.zip` during fixture teardown -- after the spec's `afterEach` AND after
# its `afterAll`. Measured 2026-09-09 with a throwaway spec: the run's
# outputDir held no `.zip` at either hook. So the spec structurally cannot copy
# its own trace, and the only two alternatives are worse:
#
#   * Stopping tracing by hand from the spec DOES write the file, and also
#     fails the test -- `Must start tracing before stopping` -- because it
#     collides with Playwright's own trace fixture. An observation instrument
#     must not go red over its own evidence handling.
#   * A `globalTeardown` addition would work, and it lives in the shared
#     `playwright.config.ts`, so it would change the behaviour of all 43 smoke
#     specs and CI's E2E job to serve one opt-in spec. Out of proportion.
#
# The video is NOT handled here -- the spec's `afterAll` saves it directly into
# the run folder, which is measured working and needs no wrapper.
#
# Run from anywhere; paths resolve against this script.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
E2E="$(cd "$HERE/.." && pwd)"
SPEC="engagement/full-engagement.spec.ts"

cd "$E2E"

# The spec self-skips without this. Set here so launching by hand cannot
# silently produce a skipped run that exits 0 -- a shape this repo has already
# been bitten by.
export SHIELD_FULL_ENGAGEMENT=1

echo "run-engagement: launching $SPEC"
echo "run-engagement: test-results/ is cleared by Playwright at run START, so"
echo "run-engagement: any PREVIOUS run's trace is already gone by this line."

# Do not let a non-zero test result skip the preservation step: a failed run is
# exactly the run whose trace is worth most. Capture the status, preserve, then
# exit with it.
set +e
npx playwright test "$SPEC" --reporter=list
RUN_STATUS=$?
set -e

echo "run-engagement: runner exited ${RUN_STATUS}"

# The newest engagement folder is this run's. The spec stamps the folder at
# test start and appends a retry suffix, so "newest by mtime" is the attempt
# that ran last -- which is the attempt whose trace is in test-results/.
RUN_DIR="$(ls -1dt artifacts/engagement-* 2>/dev/null | head -1 || true)"

if [ -z "$RUN_DIR" ]; then
  echo "run-engagement: NO RUN FOLDER under artifacts/. The spec did not reach"
  echo "run-engagement: its first step -- check for a skip or a startup failure."
  exit "$RUN_STATUS"
fi

echo "run-engagement: run folder ${RUN_DIR}"

copied=0
while IFS= read -r zip; do
  [ -n "$zip" ] || continue
  # Name the trace after the directory Playwright put it in, so a retry's trace
  # cannot overwrite the first attempt's.
  base="$(basename "$(dirname "$zip")")"
  cp "$zip" "${RUN_DIR}/trace-${base}.zip"
  echo "run-engagement: preserved trace-${base}.zip"
  copied=$((copied + 1))
done < <(find test-results -name '*.zip' -type f 2>/dev/null)

if [ "$copied" -eq 0 ]; then
  # Loud, not silent. A run with no trace is a run whose failures cannot be
  # replayed, and that must not be something you discover a week later.
  echo "run-engagement: WARNING -- no trace zip found under test-results/."
  echo "run-engagement: The recording and step log are still in ${RUN_DIR},"
  echo "run-engagement: but this run cannot be replayed in the trace viewer."
fi

echo "run-engagement: preserved ${copied} trace file(s) into ${RUN_DIR}"
echo "run-engagement: contents:"
ls -la "$RUN_DIR"

exit "$RUN_STATUS"
