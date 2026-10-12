"""The forkserver's preload for egress-redaction children (#552).

Imported ONLY by the forkserver process (`isolation._FORKSERVER_PRELOAD`), before
it forks any child: it loads the redactor once, so a child starts warm, and
scrubs the forkserver's `os.environ`. The scrub is the second line, not the
first: the forkserver is started through `env -i` with only PATH and LANG
(`isolation._use_clean_executable`), so the api's variables never reach its
environment block at all. A scrub alone would not do that: deleting from
`os.environ` leaves the original strings in the block a forked child inherits.

Importing it anywhere else would scrub THAT process's environment, so it
refuses to run in a process that has loaded the api's settings. The forkserver
ignores an ImportError from a preload, which is why the child scrubs again
(`_redaction_child.child_main`) rather than trusting this one.
"""

from __future__ import annotations

import sys

if "app.config" in sys.modules:
    raise ImportError(
        "app.ai._redaction_forkserver is the redaction forkserver's preload; "
        "importing it in the api process would scrub the api's environment"
    )

import app.ai.redact  # noqa: E402,F401 - preloaded so children start warm
from app.ai._redaction_child import scrub_environment  # noqa: E402

scrub_environment()
