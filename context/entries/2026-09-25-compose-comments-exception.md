# 2026-09-25: a compose diff that changes no parsed YAML does not trip condition 5

Branch `track1/compose-comments`, branch-start base `06fa7ce`.

## Why

#530's whole `docker-compose.yml` diff was comments, and it still came back to
the owner under condition 5. The owner chose this narrow exception over #559's
general executable-line rule, which was closed unmerged: the same measured
gain (one PR in thirty) for a fraction of the surface.

## What changed

- **`apps/api/scripts/compose_unchanged.py BASE..HEAD`**: exit 0 if every
  changed `docker-compose*.yml` parses to the same YAML node tree, 1 if any
  changed in content (an added or deleted file counts), 2 if it could not look.
  It says nothing about other condition-5 paths, and its output says so. The
  node key includes whether each scalar is plain or quoted, so a quote flip
  such as `"0o17"` to `0o17` is content (review of `94dba49`).
  `--report` (the CI form) exits 0 for either verdict and 2 only when it could
  not look.
- **CLAUDE.md**, condition 5: the exception in one sentence. The measurement
  table gains a column, with the per-PR command in its marker.
- **D-095** records the decision and the measurement.

## Measured

`compose_unchanged.py` was run on every PR in both D-059 windows that touches
a compose file. At 2026-08-26 none does, so the figure stays 4/11. At
2026-09-21 only `b516891` does. Its compose diff is form only, and its other
file is not a listed path, so the figure is 3/12 against the old 2/13.

## Proof

- `test_compose_unchanged.py`:
  - a comments-only diff;
  - content changes Python equality would hide: `on` to `yes`, `1` to `1.0`,
    `1` to `"1"`, `on` to `"on"`, and an explicit `!!str` tag;
  - quote flips where the YAML 1.1 tag agrees: `"0o17"` to `0o17`, and
    `"1e3"` to `1e3`;
  - a `!reset` tag, an added file, a deleted file, and a range with no
    compose change;
  - an unparseable file, bad arguments, a three-dot range, and `--report`
    both ways.
- Red on revert, five mutations, each red on its named test (round 2):
  loaded-object equality (`test_a_content_change_trips`), a deleted file not
  counted (`test_a_deleted_compose_file_trips`), scalar tags ignored
  (`test_a_content_change_trips`, via the explicit-tag row), scalar style
  ignored (`test_a_quote_flip_is_content_even_where_the_1_1_tag_agrees`), and
  a three-dot range accepted (`test_a_three_dot_range_is_refused_by_name`).
  In round 1, two mutations first stayed green, and the tests were
  strengthened.

## Limits

- It judges compose files only. A PR that also touches any other listed path
  still trips.
- It is not a required check. It carries the gates' crash handler, so the
  fixture harness requires a workflow to run it. It runs as its own job,
  "condition-5 compose gate read its inputs": green whenever it could look,
  including when a compose file changed (a routing fact, not a defect). The
  verdict is in the job summary. The harness cannot fixture it (it needs a git
  range), so it is DEFERRED with a reason naming each mutation's test, and it
  is in `test_gate_crash_exit_code.GATES`.
- **Why this job reports readability while #582's reports the verdict.** It is
  the same principle with the opposite design, because the rates differ.
  Condition-5 paths change in most PRs, so a job that went red whenever
  condition 5 tripped would be red almost always and would get ignored; this
  job therefore reports whether it could read its inputs. The merge rule's
  text changes rarely, so red there means something, and #582 reports the
  verdict itself. Do not "fix" either one to match the other.
