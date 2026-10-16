"""The form the model is SHOWN for each tool name, asked of the egress's own
redactor in ONE call per build (#1080, the D-111 residual recorded on #1124).

`CitationResolver` indexes a tool's shown form as an alias, and the ATT&CK
what-if compares removed and added tools by it, so each needs every name it
holds as the egress will redact it: the same mode, client name and name hints.
Before #1080 each name was redacted in the api process, one `redact_for_ai`
call per name against the tenant's whole hint set, holding the GIL in many
short calls: 17.9 s to build one resolver at 2050 hints, with other threads
waiting a median 44 ms per I/O wait for the whole build (D-111).

Scope, option (b) (advisor, #736 6221187740):

* A build that carries NAME HINTS goes through the redaction child
  (`app.ai.isolation.redact_payload_isolated`), once for all its names. That
  is the egress's own isolation, budget, places and slots: inside a Run-AI it
  uses the run's place, elsewhere it is a one-call run. A refusal (budget,
  a dead child, no capacity) is the typed `RedactionRefused` it already is,
  and nothing falls back to redacting in this process.
* A build with NO hints stays in this process: the #851 subset check behind
  the client ATT&CK dashboard, the home card, the exporters and approve. Its
  cost does not grow with the tenant's users, and routing it would let Run-AI
  load turn a client page into a 503. RESIDUAL: the org-name and address rules
  still run here over names of up to 255 characters, and nothing caps that but
  the name length (D-111).
* `mode="off"` redacts nothing, so it asks nothing.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.ai.isolation import redact_payload_isolated
from app.ai.redact import RedactionMode, redact_for_ai
from app.logging import get_logger

_log = get_logger(__name__)


def shown_forms(
    names: Iterable[str],
    *,
    mode: RedactionMode,
    client_org_name: str | None,
    name_hints: Iterable[str],
) -> dict[str, str]:
    """Each distinct name in `names`, mapped to the form the model is shown.

    With name hints this is ONE child call over all the names; without, one
    in-process `redact_for_ai` call per name (see the module docstring). Both
    run `redact_for_ai` per string with the same arguments, the child through
    `redact_payload`, so the two routes give the same forms."""
    unique = list(dict.fromkeys(n for n in names if isinstance(n, str)))
    hints = tuple(name_hints)
    if not unique or mode == "off":
        return {n: n for n in unique}
    org = client_org_name or None
    if hints:
        # Not egress: these forms are indexed, never sent, so they must not
        # make a later refusal of the same run read "sent before" (#1080 F2).
        shown, _counts = redact_payload_isolated(
            unique, mode=mode, client_org_name=org, name_hints=hints, egress=False
        )
        if not isinstance(shown, list) or len(shown) != len(unique):
            raise RuntimeError(
                f"shown_forms: the redaction child returned {type(shown).__name__} "
                f"for {len(unique)} names"
            )
        route = "isolated"
    else:
        shown = [redact_for_ai(n, mode=mode, client_org_name=org)[0] for n in unique]
        route = "in_process"
    _log.info("attack.shown_forms", route=route, names=len(unique), hints=len(hints))
    return dict(zip(unique, shown, strict=True))
