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
# selection gate, the unit suite (and its per-test count check, once #680 adds
# it), the closing-keyword and audit-evidence checks against YOUR drafted title
# and body. Each job gets a bare Python venv, as setup-python gives it, and the
# clone is HEAD merged with the base, as a pull request's checkout is. Jobs that need the
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
#     scripts/preflight.sh --title FILE --body FILE [--unit narrow|full] [--pr N] [--base REF]
#
#   --title, --body  the PR title and description you will submit (files)
#   --unit narrow    THE DEFAULT (advisor, #736 6206934217): only the test files
#                    this branch changes, plus the ones importing a module it
#                    changes. The summary says NARROW; a PR body never presents
#                    a narrow run as full. CI runs the full suite either way.
#   --unit full      CI's whole unit selection, under CI's own options. Only in a
#                    hold the coordinator has scheduled for it.
#   --pr N           an open PR: its real closing links are fetched with `gh`.
#                    Without it the linked set is taken as EMPTY, and the summary
#                    says so.
#   --base REF       default origin/main
#
# Take a container slot first (see the track brief); this starts one container
# at a time (`--memory 1500m` by default) and holds the slot for the run.
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
  echo "usage: scripts/preflight.sh --title FILE --body FILE [--unit narrow|full] [--pr N] [--base REF]" >&2
  exit 2
}

TITLE="" BODY="" UNIT="narrow" PR="0" BASE="origin/main"
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
# ONE spelling, the mixed form (C:/...), for every tool: with MSYS_NO_PATHCONV
# set, an MSYS /tmp path handed to git.exe or python.exe names a DIFFERENT
# directory (C:\tmp), and the clone landed somewhere the next line never looked.
T="$(mktemp -d)"
if command -v cygpath > /dev/null 2>&1; then T="$(cygpath -m "$T")"; fi
TM="$T"
CNAME="preflight-$$-$(date +%s)"
# An interrupted run must not leave its container holding a slot's memory.
trap 'docker rm -f "$CNAME" > /dev/null 2>&1 || true; rm -rf "$T"' EXIT
mkdir -p "$T/in" "$T/bin"
cp "$TITLE" "$T/in/title"
cp "$BODY" "$T/in/body"

# THE CLONE IS THE TREE UNDER TEST: HEAD exactly, with the base ref CI diffs
# against. A clone of a worktree carries the source's local branches as its
# remote branches, so origin/<base> is overwritten from the real ref.
#
# `reset --hard`, not `checkout`: after `clone --no-checkout` HEAD already names
# this commit, so `checkout` had nothing to do and left an EMPTY working tree
# while `HEAD^{tree}` still matched (measured 2026-10-16). So the check is on
# the files: none missing, none different.
{
  git clone -q --no-checkout "$WORKTREE" "$T/repo" \
    && git -C "$T/repo" reset -q --hard "$HEAD_SHA" \
    && git -C "$T/repo" fetch -q "$WORKTREE" "+$BASE_SHA:refs/remotes/origin/$BASE_BRANCH"
} || { echo "$P COULD NOT LOOK -- could not make the clone under test" >&2; exit 2; }
[ "$(git -C "$T/repo" rev-parse 'HEAD^{tree}')" = "$TREE_SHA" ] || { echo "$P COULD NOT LOOK -- the clone's HEAD is not this tree" >&2; exit 2; }
[ -z "$(git -C "$T/repo" status --porcelain)" ] && [ -f "$T/repo/scripts/preflight.sh" ] || {
  echo "$P COULD NOT LOOK -- the clone's working files are not HEAD's tree" >&2
  exit 2
}
# CI TESTS THE MERGE, not the branch: a pull request's checkout is the merge of
# the head into the base. So the clone merges the base in too (a no-op when the
# base is already an ancestor); a branch behind main is then tested with main's
# newer gates, as CI will test it. A conflict is could-not-look.
git -C "$T/repo" -c user.email=preflight@example.invalid -c user.name=preflight \
  merge -q --no-edit "refs/remotes/origin/$BASE_BRANCH" > /dev/null 2>&1 || {
  echo "$P COULD NOT LOOK -- $BASE does not merge cleanly into HEAD; merge it in first" >&2
  exit 2
}
MERGED_TREE="$(git -C "$T/repo" rev-parse 'HEAD^{tree}')"
echo "$P merged   HEAD + $BASE -> tree $MERGED_TREE (the tree under test)"

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
  NARROW=(--narrow-files "$TM/narrow.txt")
else
  NARROW=()
fi

# Paths handed to python, a native Windows executable under Git Bash, are in
# the mixed form: an MSYS path reaches it as \tmp\... and does not resolve.
python "$TM/repo/apps/api/scripts/preflight_plan.py" --root "$TM/repo" --out "$TM/plan" \
  --base-branch "$BASE_BRANCH" --pr-number "$PR" --unit "$UNIT" "${NARROW[@]}" > /dev/null

# What GitHub will close. Before the PR exists there is nothing to ask, and the
# empty set is stated in the summary rather than passed off as verified.
LINKED_NOTE="linked closes NOT VERIFIED (no --pr: the close guard ran without --linked)"
: > "$T/in/linked"
if [ "$PR" != "0" ]; then
  gh pr view "$PR" --json closingIssuesReferences --jq '.closingIssuesReferences[].number' > "$T/in/linked.raw" \
    || { echo "$P COULD NOT LOOK -- gh pr view $PR failed" >&2; exit 2; }
  mv "$T/in/linked.raw" "$T/in/linked"
  LINKED_NOTE="linked closes read from PR #$PR's LIVE body, not the drafted one"
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
export HOME=/tmp
git config --global --add safe.directory '*'
export CI=true GITHUB_ACTIONS=true GITHUB_WORKSPACE=/work/repo RUNNER_TEMP=/tmp/runner-temp
export GITHUB_STEP_SUMMARY=/tmp/step-summary GITHUB_ENV=/tmp/github-env GITHUB_OUTPUT=/tmp/github-output
export PREFLIGHT_TITLE_FILE=/work/in/title PREFLIGHT_BODY_FILE=/work/in/body
BASE_PATH="/work/bin:$PATH"
mkdir -p "$RUNNER_TEMP"
while IFS=$'\t' read -r idx kind wf job wd name; do
  [ -f "/work/plan/step-$idx.sh" ] || continue
  # EACH JOB GETS A BARE PYTHON, as setup-python gives a CI job: a fresh venv
  # per workflow+job, so a job that installs nothing (the audit gates) cannot
  # lean on packages the image or another job installed.
  venv="/tmp/venv-${wf%.*}-$job"
  if [ ! -x "$venv/bin/python" ]; then
    python -m venv "$venv" > /dev/null 2>&1 || { echo "PREFLIGHT-SETUP-FAILED creating $venv"; exit 2; }
  fi
  echo "::group::[$idx] $wf / $job / $name"
  s0=$(date +%s)
  (
    export PATH="$venv/bin:$BASE_PATH" VIRTUAL_ENV="$venv"
    cd "/work/repo/$wd" || exit 2
    . "/work/plan/step-$idx.env"
    exec bash --noprofile --norc -e "/work/plan/step-$idx.sh"
  )
  rc=$?
  echo "PREFLIGHT-STEP $idx $rc"
  echo "PREFLIGHT-TIME $idx $(( $(date +%s) - s0 ))"
  echo "::endgroup::"
done < /work/plan/steps.tsv
EOF
chmod +x "$T/bin/gh"
cp -R "$T/plan" "$T/plan.keep"

echo "$P running $(grep -c . "$T/plan/steps.tsv") planned step(s) in $IMAGE ..."
# Written LIVE into the git dir, so it outlives the temp dir and an interrupted
# run, and `git add -A` never sees it.
LOG="$(git rev-parse --absolute-git-dir)/preflight-last.log"
echo "$P container log: $LOG"
set +e
docker run --rm --name "$CNAME" --user 0 --memory="${SHIELD_PREFLIGHT_MEMORY:-1500m}" -v "$TM:/work" -w /work "$IMAGE" \
  bash /work/run.sh > "$LOG" 2>&1
crc=$?
set -e

if grep -q "^PREFLIGHT-SETUP-FAILED" "$LOG"; then
  echo "$P COULD NOT LOOK -- the container could not be set up (see PREFLIGHT-SETUP-FAILED in $LOG)" >&2
  exit 2
fi

# The web checks, by their own route, against the same committed tree.
glob="$(python -c "import json,re,sys; s=json.load(open(sys.argv[1]))['scripts']['format:check']; m=re.fullmatch(r'prettier --check \"([^\"]+)\"', s); print(m.group(1) if m else '')" "$TM/repo/package.json")"
[ -n "$glob" ] || { echo "$P COULD NOT LOOK -- package.json's format:check is not \`prettier --check \"<glob>\"\`" >&2; exit 2; }
v="$(bash scripts/prettier-hook.sh --print-version)" || { echo "$P COULD NOT LOOK -- could not read prettier's version from the lockfile" >&2; exit 2; }
set +e
command -v npx > /dev/null 2>&1 || { echo "$P COULD NOT LOOK -- npx is not on PATH, so prettier cannot run" >&2; exit 2; }
(cd "$T/repo" && npx -y "prettier@$v" --check "$glob") > "$T/prettier.log" 2>&1
prc=$?
# eslint, tsc and vitest take minutes. A NARROW run skips them when the branch
# touches nothing they read, and says so; FULL always runs them.
web_note="eslint, tsc, vitest"
if [ "$UNIT" = "narrow" ] && ! git diff --name-only "$BASE_SHA...$HEAD_SHA" | grep -qE '^(apps/web/|packages/|package\.json$|pnpm-lock\.yaml$|pnpm-workspace\.yaml$)'; then
  wrc="-"
  web_note="NOT RUN: NARROW, and the branch changes nothing under apps/web, packages or the pnpm files"
else
  bash scripts/verify-in-worktree.sh > "$T/web.log" 2>&1
  wrc=$?
fi
set -e

# ---- the verdict ----------------------------------------------------------
fails=0 cnl=0 ran=0
printf '\n%s %-4s %-9s %-6s %s\n' "$P" "step" "kind" "exit" "workflow / job / step"
while IFS=$'\t' read -r idx kind wf job wd name; do
  st="-"
  if [ -f "$T/plan.keep/step-$idx.sh" ]; then
    st="$(grep -E "^PREFLIGHT-STEP $idx [0-9]+$" "$LOG" | tail -1 | awk '{print $3}' || true)"
    if [ -z "$st" ]; then
      st="NONE"; cnl=$((cnl + 1))
    elif [ "$kind" = "run" ]; then
      ran=$((ran + 1))
      [ "$st" -eq 0 ] || fails=$((fails + 1))
    fi
  fi
  secs="$(grep -E "^PREFLIGHT-TIME $idx [0-9]+$" "$LOG" | tail -1 | awk '{print $3}' || true)"
  printf '%s %-4s %-9s %-6s %s / %s / %s%s\n' "$P" "$idx" "$kind" "$st" "$wf" "$job" "$name" "${secs:+ (${secs}s)}"
done < "$T/plan.keep/steps.tsv"
printf '%s %-4s %-9s %-6s %s\n' "$P" "W1" "web" "$prc" "prettier@$v --check \"$glob\""
printf '%s %-4s %-9s %-6s %s\n' "$P" "W2" "web" "$wrc" "scripts/verify-in-worktree.sh ($web_note)"
[ "$prc" -eq 0 ] || { fails=$((fails + 1)); tail -15 "$T/prettier.log"; }
web_count=2
if [ "$wrc" = "-" ]; then
  web_count=1
elif [ "$wrc" -ne 0 ]; then
  if [ "$wrc" -eq 2 ]; then cnl=$((cnl + 1)); else fails=$((fails + 1)); fi
  tail -15 "$T/web.log"
fi
[ "$crc" -eq 0 ] || echo "$P the container itself exited $crc"

verdict="PASS" code=0
if [ "$cnl" -gt 0 ]; then verdict="COULD-NOT-LOOK" code=2; elif [ "$fails" -gt 0 ]; then verdict="FAIL" code=1; fi
note=", FULL unit run"
[ "$UNIT" = "narrow" ] && note=", NARROW unit run (CI runs the full suite)"
echo ""
skipped_web=""
[ "$wrc" = "-" ] && skipped_web="; eslint/tsc/vitest NOT RUN (NARROW, no web change)"
echo "$P $verdict at $HEAD_SHA (merged with $BASE_SHA: tree $MERGED_TREE) -- $ran CI step(s) + $web_count web check(s) run, $fails failed, $cnl without an exit status; $LINKED_NOTE$note$skipped_web. Not run here: every \`github\` job above. Log: $LOG"
exit "$code"
