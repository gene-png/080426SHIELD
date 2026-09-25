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
  Its first output line names the state: UNCHANGED, CHANGED or COULD NOT
  READ. (An earlier `--report` form, which exited 0 on a change, is gone.)
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
  - an unparseable file, bad arguments and a three-dot range, each naming
    its state on the first line;
  - the CI job passing 1 and 2 through as red.
- Red on revert, five mutations, each red on its named test (round 2):
  loaded-object equality (`test_a_content_change_trips`), a deleted file not
  counted (`test_a_deleted_compose_file_trips`), scalar tags ignored
  (`test_a_content_change_trips`, via the explicit-tag row), scalar style
  ignored (`test_a_quote_flip_is_content_even_where_the_1_1_tag_agrees`), and
  a three-dot range accepted (`test_a_three_dot_range_is_refused_by_name`).
  In round 1, two mutations first stayed green, and the tests were
  strengthened. After decision (b), three more, each red on its named test: a
  change exiting 0 (`test_a_content_change_trips`), the job given a
  `--report` flag, and the job ending `exit 0`
  (`test_the_ci_job_is_red_on_a_change_and_on_could_not_read`, both).

## Limits

- It judges compose files only. A PR that also touches any other listed path
  still trips.
- It is not a required check. It carries the gates' crash handler, so the
  fixture harness requires a workflow to run it. It runs as its own job,
  "compose content changed", which reports its verdict: green is unchanged;
  red is changed (exit 1) or could not read (exit 2); the job summary names
  which. The harness cannot fixture it (it needs a git range), so it is
  DEFERRED with a reason naming each mutation's test, and it is in
  `test_gate_crash_exit_code.GATES`.
- **Why red on a change** (the owner's decision (b)). A compose content change
  is rare: of the last 80 merges on `main` (at `ef94f4f`), three touched a
  compose file, two changed its content and one was comments only. That is
  about two reds in eighty, the same rare-and-red design as #582. The owner's
  figure was four touching, two comments-only; the re-derivation (the command
  is in D-095) found three and one, and this entry uses it. An earlier draft
  of this job reported only whether it could read its inputs, on a base-rate
  sentence about condition-5 paths in general, which was the wrong
  population.
