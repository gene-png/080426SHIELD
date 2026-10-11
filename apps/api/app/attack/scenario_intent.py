"""#802: the chat box's AI reading (`attack_scenario_intent`).

The slice C matcher (`scenario.parse_change`) stays the base. Where it leaves
something not understood, the route may ask the AI for a PROPOSED change list.
The plan is #802 comment 5981734020; the advisor approved it at 16:40Z (comment
5982109105) with two conditions, both enforced here.

The AI only proposes: the answer pre-fills the picker, the admin edits and
confirms, and nothing is stored or run until Continue and Run. Every name it
returns is checked by the code Continue uses (`CitationResolver.named_by` for a
removal, `validate_added` for an addition); anything else is not understood,
never guessed.

This module is pure: no provider, no session. The route decides whether the AI
is asked at all (`routes/attack_scenarios.py`), and records the attempt.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from app.ai import redact
from app.ai.catalog_fields import redact_ai_payload
from app.ai.engine import AIResponseShapeError, parse_json_object
from app.ai.redact import RedactionMode
from app.attack import scenario
from app.attack.citations import Candidate, CitationResolver

PURPOSE = "attack_scenario_intent"

#: The answer's keys, exactly: the prompt asks for these three and no others.
_KEYS = frozenset({"remove", "add", "unclear"})

#: Every placeholder the redactor writes, read from the redactor rather than
#: listed here, so a new one is covered the day it is added.
_PLACEHOLDERS = tuple(
    sorted(
        v for k, v in vars(redact).items() if k.startswith("PLACEHOLDER_") and isinstance(v, str)
    )
)


class IntentShapeError(AIResponseShapeError):
    """The AI's answer is refused WHOLE: out of shape, or quoting words the
    admin did not write. The route returns the matcher's result with N2. An
    `AIResponseShapeError`, so it travels the same failure path as every
    other job's shape refusal."""


def available() -> bool:
    """True when the purpose is registered, i.e. its prompt is released. Until
    then the chat box is exactly slice C."""
    from app.ai.engine import registered_jobs

    return PURPOSE in registered_jobs()


def parse_answer(content: str) -> dict[str, list[str]]:
    """The job's parser: JSON, an object, exactly the three keys the prompt
    names, each a list of strings. The guard sits in the PARSER, where the
    registry-wide shape tests look for it; `read` checks the names and the
    quotes after."""
    return _shape(parse_json_object(content))


def payload(description: str, cited: Sequence[str]) -> dict[str, Any]:
    """Everything the AI is sent: the admin's text and the cited tool names.
    No vendor, category, technique or other client data."""
    return {"description": description, "tools": list(cited)}


def sent_description(
    description: str,
    cited: Sequence[str],
    *,
    redaction_mode: RedactionMode,
    client_org_name: str | None,
    name_hints: Iterable[str] = (),
) -> str:
    """The description AS THE AI RECEIVES IT: the same payload through the same
    `redact_ai_payload` call `LLMClient.invoke` makes, with the same inputs, called
    rather than repeated. Condition 1 is checked against this text."""
    cleaned, _counts = redact_ai_payload(
        payload(description, cited),
        mode=redaction_mode,
        client_org_name=client_org_name,
        name_hints=tuple(name_hints),
    )
    return cleaned["description"]


def read(
    data: Any,
    *,
    sent: str,
    cited: Sequence[str],
    client_tools: Sequence[str],
    client_org_name: str | None,
    redaction_mode: RedactionMode,
    name_hints: Iterable[str] = (),
) -> scenario.ParsedChange:
    """The AI's answer as a proposed change list, every name checked.

    Raises `IntentShapeError` when the answer is out of shape, or when an
    `unclear` phrase is not in the description sent (condition 1): either way
    nothing in it is used."""
    lists = _shape(data)
    quoted = [_quote(phrase, sent) for phrase in lists["unclear"]]
    hints = tuple(name_hints)
    resolver = CitationResolver(
        [Candidate(name=c) for c in cited],
        client_org_name=client_org_name,
        redaction_mode=redaction_mode,
        name_hints=hints,
    )
    removed: list[str] = []
    added: list[str] = []
    # A name the AI suggested that fails a check is LEFT OUT and counted,
    # never quoted: those are the AI's words, and the screen quotes only
    # what the admin wrote (Gene's ruling, #736 comment 5986057990, item 7).
    left_out = 0

    for name in lists["remove"]:
        hits = resolver.named_by(scenario.bare_name(name))
        # Exactly one cited tool, not already proposed. Anything else
        # (none, or an ambiguity) is left out; a repeat is skipped below.
        if len(hits) == 1 and next(iter(hits)) not in removed:
            removed.append(next(iter(hits)))
        elif len(hits) == 1:
            # A repeat of a tool already proposed is not "left out": the tool
            # IS in the list (#863 narrow review).
            continue
        else:
            left_out += 1

    for name in lists["add"]:
        if any(p.casefold() in name.casefold() for p in _PLACEHOLDERS):
            # The AI saw a placeholder where the admin typed a name, and the
            # name it stands for cannot be recovered for a NEW tool.
            left_out += 1
            continue
        entries = [{"name": n, "security_functions": ["detect"]} for n in added]
        entries.append({"name": scenario.bare_name(name), "security_functions": ["detect"]})
        try:
            *_, tool = scenario.validate_added(
                entries,
                client_tools=client_tools,
                client_org_name=client_org_name,
                redaction_mode=redaction_mode,
                name_hints=hints,
                limit=scenario.MAX_ADDED,
            )
        except scenario.Duplicate:
            # A second spelling of a tool already added: in the list, so not
            # "left out" (#863 narrow review).
            continue
        except (scenario.TooMany, scenario.AddedToolRefused):
            left_out += 1
            continue
        added.append(tool.name)

    return scenario.ParsedChange(
        removed=removed,
        added=added,
        not_understood=[scenario.NotUnderstood(text=q, reason="ai_unclear") for q in quoted],
        left_out=left_out,
    )


def _shape(data: Any) -> dict[str, list[str]]:
    if not isinstance(data, Mapping) or set(data) != _KEYS:
        raise IntentShapeError(f"expected exactly {sorted(_KEYS)}")
    out: dict[str, list[str]] = {}
    for key in _KEYS:
        value = data[key]
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise IntentShapeError(f"{key!r} is not a list of strings")
        out[key] = value
    return out


def _quote(phrase: str, sent: str) -> str:
    """The phrase as it stands in the description SENT, case-insensitively
    (condition 1), so the screen shows the admin's own casing. A phrase holding
    a placeholder is shown as sent: the redactor returns no span mapping, so it
    cannot be mapped back exactly (condition 2, the residual)."""
    needle = phrase.strip()
    match = re.search(re.escape(needle), sent, re.IGNORECASE) if needle else None
    if match is None:
        raise IntentShapeError("an unclear phrase is not in the description sent")
    return sent[match.start() : match.end()]
