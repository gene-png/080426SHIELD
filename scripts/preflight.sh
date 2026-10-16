#!/usr/bin/env bash
#
# Run, before a push, what CI will run on the pull request -- so CI is not
# where an error is first found (#736, 6204543223 item 4).
#
# ## What it runs
#
# The CI steps are DERIVED, not listed: `apps/api/scripts/preflight_plan.py`
# reads every `pull_request` workflow and plans each job whose steps the API
# image can run (today: ci.yml's Python job and every audit-gate.yml job),
# every `run:` step in order -- install, ruff, black, bandit, every gate, CI's
# selection gate, the unit suite and its count check, the closing-keyword and
# audit-evidence checks against YOUR drafted title and body. Jobs that need the
# composed stack, a browser or the web toolchain stay on GitHub and are listed.
# The web checks run by their own route: prettier (the lockfile's version, the
# glob from package.json's `format:check`) and `scripts/verify-in-worktree.sh`
# (eslint, tsc, vitest). `next build`, E2E, Demo and the secret scan are NOT run
# here; the summary names them.
#
# Every step runs against a CLEAN CLONE of this worktree's HEAD, in one
# throwaway `docker run --rm` on the `shield-v2-api` image (no shared stack, no
# compose). The tree must be clean: a preflight of files you have not committed
# is a preflight of something you will not push.
#
# ## Usage (Git Bash; the docker CLI on PATH)
#
#     scripts/preflight.sh --title FILE --body FILE --unit full|narrow [--pr N] [--base REF]
#
#   --title, --body  the PR title and description you will submit (files)
#   --unit full      CI's whole unit selection, under CI's own options
#   --unit narrow    only the test files this branch changes, plus the ones
#                    importing a module it changes; the summary says NARROW.
#                    CI runs the full suite either way.
#   --pr N           an open PR: its real closing links are fetched with `gh`.
#                    Without it the linked set is taken as EMPTY, and the summary
#                    says so.
#   --base REF       default origin/main
#
# Take the shared docker lock first (see the track brief); this starts one
# container and holds it for the run.
#
# ## Exit codes (D-090)
#
#     0  every planned step ran and exited 0 (advisory steps aside)
#     1  at least one step failed
#     2  could not look: bad usage, a dirty tree, an unplannable workflow, a
#        step with no recorded exit status, or no docker / image
#
# A step that was planned and left no exit status is a FAILURE (2), never a
# pass: the container prints `PREFLIGHT-STEP <n> <status>` after each one, and
# a missing line means the step never finished.
set -euo pipefail

usage() {
  echo "usage: scripts/preflight.sh --title FILE --body FILE --unit full|narrow [--pr N] [--base REF]" >&2
  exit 2
}

TITLE="" BODY="" UNIT="" PR="0" BASE="origin/main"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --title | --body | --unit | --pr | --base)
      [ "$#" -ge 2 ] && [ -n "$2" ] || { echo "FAIL: $1 needs a value" >&2; usage; }
      case "$1" in
        --title) TITLE="$2" ;;
        --body) BODY="$2" ;;
        --unit) UNIT="$2" ;;
        --pr) PR="$2" ;;
        --base) BASE="$2" ;;
      esac
      shift 2 ;;
    *) echo "FAIL: unknown argument '$1'" >&2; usage ;;
  esac
done
[ -n "$TITLE" ] && [ -n "$BODY" ] && [ -n "$UNIT" ] || usage
case "$UNIT" in full | narrow) ;; *) echo "FAIL: --unit must be full or narrow" >&2; usage ;; esac
[[ "$PR" =~ ^[0-9]+$ ]] || { echo "FAIL: --pr must be a number" >&2; usage; }
[ -s "$TITLE" ] || { echo "FAIL: could not look -- the title file '$TITLE' is missing or empty" >&2; exit 2; }
[ -s "$BODY" ] || { echo "FAIL: could not look -- the body file '$BODY' is missing or empty" >&2; exit 2; }
command -v docker > /dev/null 2>&1 || {
  echo "FAIL: could not look -- docker is not on PATH." >&2
  echo "  Git Bash: export PATH=\"\$PATH:/c/Program Files/Docker/Docker/resources/bin\"" >&2
  exit 2
}

P="preflight:"
export MSYS_NO_PATHCONV=1
WORKTREE="$(git rev-parse --show-toplevel)"
cd "$WORKTREE"
dirty="$(git status --porcelain | wc -l | tr -d '[:space:]')"
if [ "$dirty" -ne 0 ]; then
  echo "$P COULD NOT LOOK -- the tree has $dirty uncommitted path(s). Commit first: a preflight" >&2
  echo "  of files you have not committed is a preflight of something you will not push." >&2
  exit 2
fi
HEAD_SHA="$(git rev-parse HEAD)"
TREE_SHA="$(git rev-parse 'HEAD^{tree}')"
BASE_SHA="$(git rev-parse --verify --quiet "$BASE^{commit}")" || { echo "$P COULD NOT LOOK -- base '$BASE' does not resolve" >&2; exit 2; }
case "$BASE" in
  origin/*) BASE_BRANCH="${BASE#origin/}" ;;
  *) echo "$P COULD NOT LOOK -- --base must be a remote-tracking ref (origin/<branch>), as CI's origin/\${{ github.base_ref }} is" >&2; exit 2 ;;
esac
IMAGE="${SHIELD_PREFLIGHT_IMAGE:-shield-v2-api:latest}"
docker image inspect "$IMAGE" > /dev/null 2>&1 || { echo "$P COULD NOT LOOK -- image '$IMAGE' is not available (this script never builds it)" >&2; exit 2; }

echo "$P worktree $WORKTREE"
echo "$P HEAD     $HEAD_SHA"
echo "$P tree     $TREE_SHA (clean)"
echo "$P base     $BASE = $BASE_SHA"
echo "$P unit     $UNIT"

# A path docker.exe can mount: Git Bash's mktemp gives an MSYS path it cannot.
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
if command -v cygpath > /dev/null 2>&1; then TM="$(cygpath -m "$T")"; else TM="$T"; fi
mkdir -p "$T/in" "$T/bin"
cp "$TITLE" "$T/in/title"
cp "$BODY" "$T/in/body"

# THE CLONE IS THE TREE UNDER TEST: HEAD exactly, with the base ref CI diffs
# against. A clone of a worktree carries the source's local branches as its
# remote branches, so origin/<base> is overwritten from the real ref.
git clone -q --no-checkout "$WORKTREE" "$T/repo"
git -C "$T/repo" checkout -q --detach "$HEAD_SHA"
git -C "$T/repo" fetch -q "$WORKTREE" "+$BASE_SHA:refs/remotes/origin/$BASE_BRANCH"
[ "$(git -C "$T/repo" rev-parse 'HEAD^{tree}')" = "$TREE_SHA" ] || { echo "$P COULD NOT LOOK -- the clone's tree is not HEAD's" >&2; exit 2; }

# --unit narrow: the test files this branch changes, and those importing a
# module it changes (by dotted name or by stem: over-inclusion is safe here).
if [ "$UNIT" = "narrow" ]; then
  : > "$T/narrow.txt"
  while IFS= read -r f; do
    case "$f" in
      apps/api/tests/unit/test_*.py) [ -f "$f" ] && echo "${f#apps/api/}" >> "$T/narrow.txt" ;;
      apps/api/app/*.py | apps/api/scripts/*.py)
        mod="${f#apps/api/}"; mod="${mod%.py}"; mod="${mod//\//.}"; stem="${mod##*.}"
        grep -lE "(^|[^A-Za-z0-9_])(${mod//./\\.}|$stem)([^A-Za-z0-9_]|$)" apps/api/tests/unit/test_*.py 2> /dev/null \
          | sed 's#^apps/api/##' >> "$T/narrow.txt" || true ;;
    esac
  done < <(git diff --name-only "$BASE_SHA...$HEAD_SHA")
  sort -u -o "$T/narrow.txt" "$T/narrow.txt"
  n="$(wc -l < "$T/narrow.txt" | tr -d '[:space:]')"
  if [ "$n" -eq 0 ]; then
    echo "$P COULD NOT LOOK -- --unit narrow found no test file this branch changes or reaches." >&2
    echo "  Use --unit full; a run of nothing is not a pass." >&2
    exit 2
  fi
  echo "$P narrow   $n test file(s): $(tr '\n' ' ' < "$T/narrow.txt")"
  NARROW=(--narrow-files "$T/narrow.txt")
else
  NARROW=()
fi

python "$T/repo/apps/api/scripts/preflight_plan.py" --root "$T/repo" --out "$T/plan" \
  --base-branch "$BASE_BRANCH" --pr-number "$PR" --unit "$UNIT" "${NARROW[@]}" > /dev/null

# What GitHub will close. Before the PR exists there is nothing to ask, and the
# empty set is stated in the summary rather than passed off as verified.
LINKED_NOTE="linked closes taken as EMPTY (no --pr)"
: > "$T/in/linked"
if [ "$PR" != "0" ]; then
  gh pr view "$PR" --json closingIssuesReferences --jq '.closingIssuesReferences[].number' > "$T/in/linked.raw" \
    || { echo "$P COULD NOT LOOK -- gh pr view $PR failed" >&2; exit 2; }
  mv "$T/in/linked.raw" "$T/in/linked"
  LINKED_NOTE="linked closes read from PR #$PR"
fi
# The only `gh` call a planned step makes is the close guard's. Anything else
# is refused by name rather than answered.
cat > "$T/bin/gh" << 'EOF'
#!/usr/bin/env bash
if [ "$1 $2" = "pr view" ] && [ "${4:-}" = "--json" ] && [ "${5:-}" = "closingIssuesReferences" ]; then
  cat /work/in/linked
  exit 0
fi
echo "preflight gh shim: only 'gh pr view N --json closingIssuesReferences' is provided; got: $*" >&2
exit 2
EOF

# One container, every planned step in order. Each step runs as GitHub runs
# it, `bash --noprofile --norc -e`, in its working directory, with its env.
cat > "$T/run.sh" << 'EOF'
set -u
export DEBIAN_FRONTEND=noninteractive
if ! { apt-get update -qq > /tmp/apt.log 2>&1 && apt-get install -y -qq git nodejs > /tmp/apt.log 2>&1; }; then
  echo "PREFLIGHT-SETUP-FAILED installing git and nodejs"; tail -5 /tmp/apt.log; exit 2
fi
git config --global --add safe.directory '*'
export CI=true GITHUB_ACTIONS=true GITHUB_WORKSPACE=/work/repo RUNNER_TEMP=/tmp/runner-temp
export GITHUB_STEP_SUMMARY=/tmp/step-summary GITHUB_ENV=/tmp/github-env GITHUB_OUTPUT=/tmp/github-output
export PREFLIGHT_TITLE_FILE=/work/in/title PREFLIGHT_BODY_FILE=/work/in/body
export PATH="/work/bin:$PATH" HOME=/tmp
mkdir -p "$RUNNER_TEMP"
while IFS=$'\t' read -r idx kind wf job wd name; do
  [ -f "/work/plan/step-$idx.sh" ] || continue
  echo "::group::[$idx] $wf / $job / $name"
  (
    cd "/work/repo/$wd" || exit 2
    . "/work/plan/step-$idx.env"
    exec bash --noprofile --norc -e "/work/plan/step-$idx.sh"
  )
  echo "PREFLIGHT-STEP $idx $?"
  echo "::endgroup::"
done < /work/plan/steps.tsv
EOF
chmod +x "$T/bin/gh"
cp -R "$T/plan" "$T/plan.keep"

echo "$P running $(grep -c . "$T/plan/steps.tsv") planned step(s) in $IMAGE ..."
set +e
docker run --rm --user 0 --memory="${SHIELD_PREFLIGHT_MEMORY:-4g}" -v "$TM:/work" -w /work "$IMAGE" \
  bash /work/run.sh > "$T/container.log" 2>&1
crc=$?
set -e
# Kept after the temp dir goes: inside the git dir, so `git add -A` never sees it.
LOG="$(git rev-parse --absolute-git-dir)/preflight-last.log"
cp "$T/container.log" "$LOG"

if grep -q "^PREFLIGHT-SETUP-FAILED" "$T/container.log"; then
  echo "$P COULD NOT LOOK -- the container could not install git and nodejs (network?). Log: $LOG" >&2
  exit 2
fi

# The web checks, by their own route, against the same committed tree.
glob="$(python -c "import json,re,sys; s=json.load(open(sys.argv[1]))['scripts']['format:check']; m=re.fullmatch(r'prettier --check \"([^\"]+)\"', s); print(m.group(1) if m else '')" "$T/repo/package.json")"
[ -n "$glob" ] || { echo "$P COULD NOT LOOK -- package.json's format:check is not \`prettier --check \"<glob>\"\`" >&2; exit 2; }
v="$(bash scripts/prettier-hook.sh --print-version)" || { echo "$P COULD NOT LOOK -- could not read prettier's version from the lockfile" >&2; exit 2; }
set +e
(cd "$T/repo" && npx -y "prettier@$v" --check "$glob") > "$T/prettier.log" 2>&1
prc=$?
bash scripts/verify-in-worktree.sh > "$T/web.log" 2>&1
wrc=$?
set -e

# ---- the verdict ----------------------------------------------------------
fails=0 cnl=0 ran=0
printf '\n%s %-4s %-9s %-6s %s\n' "$P" "step" "kind" "exit" "workflow / job / step"
while IFS=$'\t' read -r idx kind wf job wd name; do
  st="-"
  if [ -f "$T/plan.keep/step-$idx.sh" ]; then
    st="$(grep -E "^PREFLIGHT-STEP $idx [0-9]+$" "$T/container.log" | tail -1 | awk '{print $3}')"
    if [ -z "$st" ]; then
      st="NONE"; cnl=$((cnl + 1))
    elif [ "$kind" = "run" ]; then
      ran=$((ran + 1))
      [ "$st" -eq 0 ] || fails=$((fails + 1))
    fi
  fi
  printf '%s %-4s %-9s %-6s %s / %s / %s\n' "$P" "$idx" "$kind" "$st" "$wf" "$job" "$name"
done < "$T/plan.keep/steps.tsv"
printf '%s %-4s %-9s %-6s %s\n' "$P" "W1" "web" "$prc" "prettier@$v --check \"$glob\" (log: tail below on failure)"
printf '%s %-4s %-9s %-6s %s\n' "$P" "W2" "web" "$wrc" "scripts/verify-in-worktree.sh (eslint, tsc, vitest)"
[ "$prc" -eq 0 ] || { fails=$((fails + 1)); tail -15 "$T/prettier.log"; }
[ "$wrc" -eq 0 ] || { [ "$wrc" -eq 2 ] && cnl=$((cnl + 1)) || fails=$((fails + 1)); tail -15 "$T/web.log"; }
[ "$crc" -eq 0 ] || echo "$P the container itself exited $crc"

verdict="PASS" code=0
if [ "$cnl" -gt 0 ]; then verdict="COULD-NOT-LOOK" code=2; elif [ "$fails" -gt 0 ]; then verdict="FAIL" code=1; fi
note=""
[ "$UNIT" = "narrow" ] && note=", NARROW unit run (CI runs the full suite)"
echo ""
echo "$P $verdict at $HEAD_SHA tree $TREE_SHA vs $BASE_SHA -- $ran CI step(s) + 2 web check(s) run, $fails failed, $cnl without an exit status; $LINKED_NOTE$note. Not run here: every \`github\` job above. Log: $LOG"
exit "$code"
