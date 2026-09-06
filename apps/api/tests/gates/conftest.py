"""Keep pytest out of the gate fixtures: these are INPUTS, not tests.

`pyproject.toml` sets `testpaths = ["tests"]`, so a bare `pytest` from `apps/api`
walks this directory. Two fixtures are named `test_*.py` because the gate they
exercise (`check_test_integrity`) only looks at files matching that pattern --
renaming them would make the fixtures invisible to the thing they test.

Collecting them fails, and for a reason that has nothing to do with whatever the
developer was doing: `check_test_integrity/2026-08-private-constant-import/tests/
test_csf_ai_contract.py` imports `_PARSER_ROW_KEYS` from `app.csf.playbook`, and
that symbol does not exist there. It is not supposed to. The file is a verbatim
reproduction of the #72 instance -- a contract test built from the parser's own
constants -- preserved so `check_gate_fixtures.py` can assert the gate exits 1 on
it. A fixture that imported something real would be a different fixture.

So the collection error is a property of the corpus, not a defect in it: a
fixture corpus of deliberate violations is visible to every scanner that walks
the tree, and each one needs a decision. The others are handled where they live
-- `pyproject.toml` for ruff and black, `_SKIP_PATHS` for the control-character
sweep, `_is_gate_fixture` for test-integrity -- and this file is pytest's.

LOAD-BEARING ON THE HARNESS RUNNING. These files are kept honest by
`check_gate_fixtures` asserting their exit codes in CI, not by any scanner
reading them. If the "gates can fail" step is removed, skipped, or made
`continue-on-error`, this exclusion loses its justification along with the rest.

Note CI is unaffected either way: it runs `pytest -m unit tests/unit`, which is
path-scoped away from here. This exists for the local `pytest` a developer runs
by hand, which `docs/development.md` documents without a path.
"""

from __future__ import annotations

collect_ignore_glob = ["*"]
