"""PII redactor - the SECURITY BOUNDARY in front of every LLM call.

Master Spec §12 + §12.1. SHIELD v1 accepts the risk of egress to a
commercial LLM provider (Anthropic Claude by default); this module is
the primary compensating control. It is intentionally pure: no I/O, no
DB, no clock. It can be reviewed line-by-line in an OWASP audit.

Functions:
  redact_for_ai(text, *, mode, client_org_name=None, name_hints=())
      -> (cleaned_text, removed_counts)
  redact_payload(obj, *, mode, client_org_name=None, name_hints=())
      -> (cleaned_obj, removed_counts)

`removed_counts` is a dict like `{"email": 3, "phone": 1, ...}`. It
becomes the `removed_items` JSON column on `artifact_redactions` (Master
Spec §11) and gets logged on the corresponding `llm_calls` audit row.
Counts only - no payload contents.

Modes:
  strict   - removes everything below.
  standard - removes everything EXCEPT addresses and the client's org name.
             Useful when the prompt explicitly needs the org context.
  off      - pass-through. Refused at startup outside development by
             config.assert_safe_for_runtime() (Phase 1). This module
             accepts `off` so unit tests can compare "redacted vs raw"
             paths; production never reaches here with mode=off.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any, Literal

RedactionMode = Literal["strict", "standard", "off"]

# ---------------------------------------------------------------------------
# Replacement placeholders
# ---------------------------------------------------------------------------

PLACEHOLDER_EMAIL = "[EMAIL]"
PLACEHOLDER_PHONE = "[PHONE]"
PLACEHOLDER_SSN = "[SSN]"
PLACEHOLDER_EIN = "[EIN]"
PLACEHOLDER_CAGE = "[CAGE]"
PLACEHOLDER_CONTRACT = "[CONTRACT]"
PLACEHOLDER_ADDRESS = "[ADDRESS]"
PLACEHOLDER_NAME = "[NAME]"
PLACEHOLDER_CLIENT = "[CLIENT]"
PLACEHOLDER_SIGNATURE = "[SIGNATURE_BLOCK]"

# ---------------------------------------------------------------------------
# Regexes. Compiled once at import. Designed to favor false-positives
# (over-redact) over false-negatives (leak), because this is a security
# boundary and we'd rather lose some fidelity than leak PII.
# ---------------------------------------------------------------------------

_RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")

# Phones: matches any "phone-shaped" run - optional `+`, 10-20 chars of
# digits plus the usual separators. Order matters: SSN / EIN / contract /
# CAGE patterns run before phone so they remove their substrings first
# and the phone pass doesn't double-strike.
_RE_PHONE = re.compile(
    r"""
    (?<!\d)                              # not in the middle of a longer digit run
    \+?[\d]                              # opens with optional + then a digit
    [\d\s.\-()]{8,18}                    # 8-18 more digit-or-separator chars
    \d                                   # ends with a digit
    """,
    re.VERBOSE,
)

_RE_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_RE_EIN = re.compile(r"\b\d{2}-\d{7}\b")

# CAGE code: exactly 5 alphanumeric characters, often introduced as
# "CAGE 1A2B3" or just "1A2B3" in a list. The introducer keyword form is
# the only one we redact - the bare 5-char-alnum is too generic to flag
# without a huge false-positive rate.
_RE_CAGE = re.compile(r"\bCAGE[\s:#-]*([A-Z0-9]{5})\b", re.IGNORECASE)

# Contract numbers: common govcon shapes include W91QUZ-23-C-0001,
# HQ0034-22-D-0007, FA8732-21-F-1234. The prefix mixes letters and
# digits (e.g. W91QUZ) so it's [A-Z0-9]{4,8}, not [A-Z]{2,6}.
_RE_CONTRACT = re.compile(
    r"\b[A-Z0-9]{4,8}-\d{2}-[A-Z]-\d{4,5}[A-Z]?\b",
)

_SIGNATURE_OPENERS = (
    "sincerely",
    "regards",
    "best regards",
    "kind regards",
    "best",
    "thanks",
    "thank you",
    "cheers",
    "respectfully",
    "v/r",
)


def _count_replacements(pattern: re.Pattern[str], text: str) -> int:
    return sum(1 for _ in pattern.finditer(text))


def _redact_signature_blocks(text: str) -> tuple[str, int]:
    """Strip everything from a signature opener line to end of input.

    Each line is checked. The first signature opener we see is the cut
    point - everything from that line onward becomes the placeholder.
    """
    lines = text.splitlines(keepends=True)
    cut: int | None = None
    for idx, raw in enumerate(lines):
        stripped = raw.strip().lower().rstrip(",.!")
        if stripped in _SIGNATURE_OPENERS:
            cut = idx
            break
    if cut is None:
        return text, 0
    head = "".join(lines[:cut])
    return head + PLACEHOLDER_SIGNATURE + "\n", 1


def _redact_addresses(text: str) -> tuple[str, int]:
    """Best-effort street-address redaction.

    Looks for lines that have a leading digit run + street keyword OR
    a line containing "Suite", "Apt", "PO Box". This is heuristic and
    deliberately over-eager; tests cover the realistic shapes.
    """
    street_words = (
        "Street",
        "St",
        "Avenue",
        "Ave",
        "Road",
        "Rd",
        "Drive",
        "Dr",
        "Lane",
        "Ln",
        "Boulevard",
        "Blvd",
        "Court",
        "Ct",
        "Way",
        "Highway",
        "Hwy",
        "Parkway",
        "Pkwy",
        "Plaza",
        "Square",
    )
    street_pat = r"\b\d{1,6}\s+([A-Z][A-Za-z]+\s+){1,4}(?:" + "|".join(street_words) + r")\b"
    suite_pat = r"\b(?:Suite|Ste|Apt|Unit|Floor|Fl|PO\s+Box|P\.O\.\s+Box)[\s.#]*[A-Za-z0-9\-]+"
    combined = re.compile(f"{street_pat}|{suite_pat}", re.IGNORECASE)
    count = _count_replacements(combined, text)
    if count == 0:
        return text, 0
    return combined.sub(PLACEHOLDER_ADDRESS, text), count


def _redact_org_name(text: str, org_name: str) -> tuple[str, int]:
    """Replace the client's legal name (case-insensitive, whole-token)."""
    if not org_name.strip():
        return text, 0
    pat = re.compile(rf"\b{re.escape(org_name)}\b", re.IGNORECASE)
    count = _count_replacements(pat, text)
    if count == 0:
        return text, 0
    return pat.sub(PLACEHOLDER_CLIENT, text), count


def _redact_names(text: str, name_hints: Iterable[str]) -> tuple[str, int]:
    """Replace exact-match names from `name_hints` (case-insensitive)."""
    hints = [h for h in name_hints if h and len(h) >= 2]
    if not hints:
        return text, 0
    pat = re.compile(
        r"\b(?:" + "|".join(re.escape(h) for h in hints) + r")\b",
        re.IGNORECASE,
    )
    count = _count_replacements(pat, text)
    if count == 0:
        return text, 0
    return pat.sub(PLACEHOLDER_NAME, text), count


def redact_for_ai(
    text: str,
    *,
    mode: RedactionMode = "strict",
    client_org_name: str | None = None,
    name_hints: Iterable[str] = (),
) -> tuple[str, dict[str, int]]:
    """Redact PII from `text`. Returns the cleaned text + a counts dict.

    `mode="off"` returns the original text and an empty counts dict.
    Production refuses `off` via `Settings.assert_safe_for_runtime`.
    """
    counts: dict[str, int] = {}
    if mode == "off":
        return text, counts

    # Signature blocks first: they hide tail content from being redacted
    # twice when the block contains names + phones + emails.
    cleaned, c = _redact_signature_blocks(text)
    if c:
        counts["signature_block"] = c

    for key, pat, placeholder in (
        ("email", _RE_EMAIL, PLACEHOLDER_EMAIL),
        ("ssn", _RE_SSN, PLACEHOLDER_SSN),
        ("ein", _RE_EIN, PLACEHOLDER_EIN),
        ("contract", _RE_CONTRACT, PLACEHOLDER_CONTRACT),
        ("phone", _RE_PHONE, PLACEHOLDER_PHONE),
    ):
        c = _count_replacements(pat, cleaned)
        if c:
            cleaned = pat.sub(placeholder, cleaned)
            counts[key] = c

    # CAGE: keep only the placeholder, not the introducer keyword.
    cage_count = _count_replacements(_RE_CAGE, cleaned)
    if cage_count:
        cleaned = _RE_CAGE.sub(PLACEHOLDER_CAGE, cleaned)
        counts["cage"] = cage_count

    # Name hints
    cleaned, c = _redact_names(cleaned, name_hints)
    if c:
        counts["name"] = c

    if mode == "strict":
        # Addresses + org name only in strict mode.
        cleaned, c = _redact_addresses(cleaned)
        if c:
            counts["address"] = c
        if client_org_name:
            cleaned, c = _redact_org_name(cleaned, client_org_name)
            if c:
                counts["client_org"] = c

    return cleaned, counts


def redact_payload(
    obj: Any,
    *,
    mode: RedactionMode = "strict",
    client_org_name: str | None = None,
    name_hints: Iterable[str] = (),
) -> tuple[Any, dict[str, int]]:
    """Recursively redact strings inside an arbitrary JSON-shaped payload.

    Returns the cleaned object + a counts dict aggregated across every
    string encountered. dict keys are not redacted (they're typically
    field names like "email", which we want preserved).
    """
    totals: dict[str, int] = {}

    def _walk(node: Any) -> Any:
        if isinstance(node, str):
            cleaned, counts = redact_for_ai(
                node,
                mode=mode,
                client_org_name=client_org_name,
                name_hints=name_hints,
            )
            for key, value in counts.items():
                totals[key] = totals.get(key, 0) + value
            return cleaned
        if isinstance(node, Mapping):
            return {k: _walk(v) for k, v in node.items()}
        if isinstance(node, (list, tuple)):
            return type(node)(_walk(v) for v in node)
        return node

    return _walk(obj), totals
