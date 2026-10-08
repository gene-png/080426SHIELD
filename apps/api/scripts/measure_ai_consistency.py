"""Run one AI job N times on the same input and report how far the runs agree.

#806 step 1: the before-and-after measure every later prompt change is judged
by. Usage, inside a container that can reach no shared service:

    python -m scripts.measure_ai_consistency --job zt_score --framework cisa \
        --runs 2 --out /tmp/zt.json

WHAT IT REFUSES (exit 2), before any model call:
  * a DATABASE_URL that is not SQLite. A run writes `llm_calls` rows, and the
    compose file hardcodes the shared Postgres -- `docker compose run --no-deps`
    from ANY worktree joins that network -- so the only safe database is a
    throwaway file;
  * SHIELD_LLM_MODE other than `live`. Fixture mode echoes canned responses, so
    it would report perfect agreement about nothing;
  * SHIELD_REDACTION_MODE other than `strict`;
  * for tech_debt_extract, a run without `--service-id`: the inventory file
    names no client, and redaction replaces the NAMED service's client's names,
    so whose names those are is never guessed.

WHAT IT DOES: builds the payload with the route's own builder
(`routes/zt.py::_zt_ai_request_for`, `routes/csf.py::_csf_ai_request_for`,
`routes/attack.py::_attack_ai_request_for`; for tech_debt_extract the rows of
`--inventory`, parsed by the upload's own `parse_inventory`) and calls the
model the way the route does -- `engine.run_job` inside `ai_call_boundary` for
zt_score, `run_batches` over `_csf_batch_inputs` for csf_score,
`_run_mitre_map_batched` for mitre_map, `extract_from_rows` for
tech_debt_extract -- so redaction, mode, batching and output caps are
production's. It parses with the job's registered parser.
It APPLIES NOTHING: no answer, coverage row or capability item is written. The
one state change it can make is `--reopen-released`, which sets a released
assessment back to DRAFT so the route's builder will accept it -- the demo seed
releases every assessment -- and which the report records as `input_setup`.

WHAT IT REPORTS, per pair of successful runs: the row set (in both / only in
one / unreadable / duplicated keys), and per field over rows present in both,
how many were compared and how many agreed. Every share carries its
denominator. It also reports the number the client would see, computed by the
engines rather than here: zt_score's gap count (`zt.scoring.analyze_gaps`),
csf_score's per-row maturity level (`csf.playbook.score_tier`), mitre_map's
per-technique R3 status (`attack.computed.status_from`, over citations resolved
by the run's own `CitationResolver`), with agreement on the level or status per
pair, and tech_debt_extract's reconciliation (`reconcile_rows`). A value the
APPLY path would refuse is compared and never agreement (`_absence`); deciding
that needs, for zt_score, the framework's top stage, and for mitre_map, the
assessment's codes and the run's resolver (`AttackScope`), and a comparison
without them is refused rather than guessed (`_require_context`). List fields
(tool lists, `security_functions`) are compared as SETS, with a mean Jaccard. For zt_score it reports how often the model
repeated the `current` stage it was sent (`echo`). Counts and codes only: no
model text reaches the output or the logs.

THE DOLLAR GUARD (#952 review F1): every invocation is one side (before or
after) of a service's pair, and gets half that service's #806 cost cap
(`COST_CAPS_USD`, `side_cap_usd`). Before each run after the first, the spend so
far plus the largest single run so far -- input and output at list price, from
the `llm_calls` rows -- must stay within it, or the run is not started
(`stopped_budget`). It is a projection: a run larger than every earlier one can
still cross the line, and the FIRST run is not bounded in advance, because
nothing is known before it. `--max-output-tokens N`, optional, additionally
starts no further run once N output tokens are spent.

THE REPORT IS KEPT (#952 review F2, narrow review 2): `--out` is reserved empty
at start, then REPLACED after every run by an atomic rename (a temporary file in
the same directory, fsynced, then `os.replace`). So the file is always either
empty (no run has completed yet) or one whole JSON report: the last one written,
holding every run completed before that write. A crash or Ctrl-C after any
provider call was started replaces it with a report marked `aborted`; if even
that write fails, the last in-progress report stays. The file is removed only
when no provider call was started at all.

PRICES: the dollar guard prices tokens at the configured provider and model's
list price (`PRICES_USD_PER_MTOK`); a model with no recorded price is refused
(`price_unknown_for_model`), and the report records the price it used.

`--probe-batches` runs only the first N of a batched job's batches. For
mitre_map, `--runs 2` or more compares runs of the same probed batches like any
measurement (#736 comment 6068587667); for csf_score a probe is one run.

The report records the DATABASE_URL's query parameters (never its path or
credentials), so a SQLite `?timeout=` the run depended on is on record.

THE SYNTHETIC CORPUS (#806 comment 5983938383, section 2): the demo seed's notes
cannot exercise the #806 prompts, so `scripts/measure_corpus/` holds a committed
synthetic one. `--notes-corpus scripts/measure_corpus/notes.json` (zt_score and
csf_score) writes its notes over the measured assessment's answer rows before
the route's builder runs -- recorded in the report as `input_setup` -- and
`--inventory scripts/measure_corpus/tech_debt_inventory.xlsx` is tech_debt_extract's
input. `{{CLIENT_NAME}}` in either is filled with the client's legal name, so the
redactor has a real client name to replace on the way out.

`--out` is created before any provider exists (#806 comment 5965052688), and
never over an existing file: an earlier report is a paid run's only record.

EXIT: 0 every run succeeded; 1 a run failed, or fewer than two succeeded -- one,
for a single-run probe (`--probe-batches` with `--runs 1`; a mitre_map probe of
two or more runs needs two, like any measurement). The report is still written,
and names each failure. 2 refused, before any provider call, each refusal with its own typed
reason -- including every input this could otherwise read as nothing to do (a
corpus that is missing, empty, malformed, for a job that reads no notes, or
landing on no row the route sends; an `--out` that exists or cannot be written).

`zt_score`, `csf_score`, `mitre_map` and `tech_debt_extract` are implemented
(#806: the last two so the "before" runs use today's prompts). Any other job is
refused rather than approximated.
"""

from __future__ import annotations

import argparse
import functools
import itertools
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.logging import get_logger

_log = get_logger(__name__)

#: Jobs with an input builder here. `_job_shape` names each one's row list, key
#: and compared fields.
_IMPLEMENTED_JOBS = ("zt_score", "csf_score", "mitre_map", "tech_debt_extract")

#: Jobs `--probe-batches` applies to: the batched ones.
_BATCHED_JOBS = ("csf_score", "mitre_map")

#: Jobs whose probe may run more than once and be COMPARED: the same probed
#: batches every run, agreement reported like a full measurement. mitre_map's
#: numbers back #479 and the cap re-derivation (#736 comment 6068587667).
_COMPARED_PROBE_JOBS = ("mitre_map",)

#: Free text, which differs in wording on every run, so never compared.
_ATTACK_FREE_TEXT = ("rationale",)
_TECH_DEBT_FREE_TEXT = ("function", "notes")
#: The PARSER's own output on an item (#878's refusal records), not a judgement
#: the model made: two runs agree on it trivially when nothing was refused, so
#: comparing it would add agreement nobody earned (#867 narrow review B1).
_TECH_DEBT_NOT_JUDGEMENTS = ("findings",)


class Refused(Exception):
    """The environment is not one a measurement may run in."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class RunRecord:
    ok: bool
    data: dict | None
    failure: str | None
    input_tokens: int | None
    output_tokens: int | None
    # B3: a failed run's typed reason is often a constant (`ai_call_failed`),
    # so the underlying exception's TYPE name is kept too -- never its message,
    # which can quote the model -- with the boundary's `charged_likely`.
    cause: str | None = None
    charged_likely: bool | None = None
    # B1 (review 2): False when any `llm_calls` row of this run has no output
    # count -- a call that failed after billing writes a FAILED row with NULL
    # tokens, and leaving it out of a sum would understate the spend in silence.
    tokens_complete: bool = True
    # #952 review F3: how many `llm_calls` rows the run wrote. 0 is a run that
    # never reached a provider -- zero spend, KNOWN -- which is not the same as
    # a run whose spend is unknown. None where nobody counted (a hand-built
    # record), which keeps the older reading: no output count is unknown.
    calls: int | None = None
    # #952 narrow review 1: how many provider calls the run STARTED, counted
    # where `LLMClient.invoke` is entered -- before its row exists. A row can
    # be missing for a call that billed (a deadline while it was in flight, a
    # failed commit after it returned), so only `started == 0` is known zero
    # spend; fewer rows than calls started is UNKNOWN spend.
    started: int | None = None


#: More runs than this is refused: every run is billed, and five pairs already
#: show an observed set rather than one value.
MAX_RUNS = 5

#: The #806 live-pass caps, USD per SERVICE: comment 5983938383, section 2's
#: table, with the $25 total approved in #736 (comment 5984022081, item 8). A
#: cap covers its service's whole before-and-after -- two invocations of this
#: script, one per side.
COST_CAPS_USD: dict[str, int] = {
    "tech_debt_extract": 3,
    "csf_score": 8,
    "zt_score": 3,
    "mitre_map": 6,
    "risk_synthesize": 5,
}

#: List prices, USD per million tokens, by (provider, model) as configured
#: (`SHIELD_LLM_PROVIDER`, `SHIELD_LLM_MODEL`). Source: the Claude API skill's
#: model table, cached 2026-10-06 (Anthropic first-party rates; section 2's
#: estimates use the claude-opus-5 row). A model not listed is REFUSED
#: (`price_unknown_for_model`): a dollar guard priced for another model is not
#: a guard. Add a row only with a cited price.
PRICES_USD_PER_MTOK: dict[tuple[str, str], dict[str, float]] = {
    ("anthropic", "claude-opus-5"): {"input": 5, "output": 25},
    ("anthropic", "claude-sonnet-5"): {"input": 2, "output": 10},
}


def price_for(provider: str, model: str) -> dict[str, float]:
    """The list price for the configured provider and model, or a refusal."""
    price = PRICES_USD_PER_MTOK.get((provider, model))
    if price is None:
        raise Refused(
            "price_unknown_for_model",
            f"No list price is recorded for {provider}/{model}; the dollar guard "
            "cannot be priced. Add a cited row to PRICES_USD_PER_MTOK first.",
        )
    return price


#: One invocation is one side (before or after) of a service's pair.
_SIDES_PER_SERVICE = 2


def side_cap_usd(job: str) -> float:
    """The dollars one invocation of `job` may spend: one side's half of its
    service's cap. `run_loop` guards it (`max_usd`)."""
    return COST_CAPS_USD[job] / _SIDES_PER_SERVICE


def _usd(input_tokens: int, output_tokens: int, price: Mapping[str, float]) -> float:
    return round((input_tokens * price["input"] + output_tokens * price["output"]) / 1e6, 6)


def _spend_known(record: RunRecord) -> bool:
    """Every call the run started is accounted for by a row with tokens."""
    if record.started == 0:
        return True
    if record.started is not None and record.calls is not None and record.calls < record.started:
        return False
    return (
        record.input_tokens is not None
        and record.output_tokens is not None
        and record.tokens_complete
    )


def run_usd(record: RunRecord, price: Mapping[str, float]) -> float | None:
    """One run's spend at list price, input AND output, from its `llm_calls`
    rows. 0 ONLY for a run that started no provider call; None (unknown) when
    a started call has no row or a row has no tokens."""
    if record.started == 0:
        return 0.0
    if not _spend_known(record):
        return None
    return _usd(record.input_tokens or 0, record.output_tokens or 0, price)


# --- the synthetic notes corpus (#806 comment 5983938383, section 2) ---------

#: Filled with the client's legal name before anything is built, so the
#: redactor has a real client name to replace: a corpus naming no client would
#: never exercise that path, and one naming a real client is client data.
CLIENT_NAME_PLACEHOLDER = "{{CLIENT_NAME}}"

#: The jobs whose payload carries interview notes. Any other job given
#: `--notes-corpus` is refused: ignoring it would report a corpus run that
#: never used the corpus.
_NOTES_JOBS = ("zt_score", "csf_score")


@dataclass(frozen=True)
class NotesCorpus:
    """A loaded `--notes-corpus`: its name, its classes in file order, each
    with its notes, and the file's sha256 (recorded, so a report names the
    exact corpus it ran on)."""

    corpus: str
    classes: tuple[tuple[str, tuple[str, ...]], ...]
    sha256: str


def _corpus_invalid(message: str) -> Refused:
    return Refused("notes_corpus_invalid", f"--notes-corpus: {message}")


def load_notes_corpus(path: str) -> NotesCorpus:
    """Read and check a notes corpus. Every input that would otherwise measure
    nothing is refused with its own reason, never read as "no notes to write":
    an unreadable path (`notes_corpus_unreadable`), an empty file or one with no
    class (`notes_corpus_empty`), and anything malformed -- a class with no
    notes, a note that is not text, a class named twice or not at all, a key
    misspelt (`notes_corpus_invalid`)."""
    import hashlib

    try:
        # An empty path reads the working directory, which is not a file: the
        # same refusal as any other path that names no readable file.
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise Refused(
            "notes_corpus_unreadable", f"--notes-corpus could not be read: {exc}"
        ) from exc
    if not raw.strip():
        raise Refused("notes_corpus_empty", "--notes-corpus is an empty file.")
    try:
        doc = json.loads(raw)
    except ValueError as exc:
        raise _corpus_invalid(f"not JSON ({exc.__class__.__name__}).") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("classes"), list):
        raise _corpus_invalid('expected an object with a "classes" list.')
    name = doc.get("corpus")
    if not (isinstance(name, str) and name):
        raise _corpus_invalid('"corpus" must name the corpus.')
    if not doc["classes"]:
        raise Refused("notes_corpus_empty", "--notes-corpus has no class.")
    classes: list[tuple[str, tuple[str, ...]]] = []
    for i, entry in enumerate(doc["classes"]):
        if not isinstance(entry, dict) or set(entry) != {"class", "notes"}:
            raise _corpus_invalid(f'class {i} must have exactly "class" and "notes".')
        cls, notes = entry["class"], entry["notes"]
        if not (isinstance(cls, str) and cls):
            raise _corpus_invalid(f"class {i} has no name.")
        if cls in {c for c, _ in classes}:
            raise _corpus_invalid(f"class {cls!r} appears twice.")
        if not (isinstance(notes, list) and notes and all(isinstance(n, str) for n in notes)):
            raise _corpus_invalid(f"class {cls!r} needs a non-empty list of text notes.")
        classes.append((cls, tuple(notes)))
    corpus = NotesCorpus(name, tuple(classes), hashlib.sha256(raw).hexdigest())
    _log.info(
        "measure_ai_consistency.notes_corpus_loaded",
        corpus=name,
        classes=len(classes),
        sha256=corpus.sha256,
    )
    return corpus


def _require_client_name(texts: Sequence[str], client_name: str | None, what: str) -> None:
    """Refuse a placeholder that cannot be filled: sent as written, it would
    reach the provider as a literal and the redactor would have no name to
    replace -- a corpus run that never tested redaction."""
    if not client_name and any(CLIENT_NAME_PLACEHOLDER in t for t in texts):
        raise Refused(
            "client_name_missing",
            f"{what} uses {CLIENT_NAME_PLACEHOLDER} and the client has no legal name to fill it.",
        )


def _fill_client_name(text: str, client_name: str | None) -> tuple[str, int]:
    """`text` with the placeholder filled, and how many were filled. Callers
    have already refused a placeholder with no name (`_require_client_name`)."""
    n = text.count(CLIENT_NAME_PLACEHOLDER)
    return (text.replace(CLIENT_NAME_PLACEHOLDER, client_name or ""), n) if n else (text, 0)


def assign_notes(keys: Sequence[str], corpus: NotesCorpus) -> dict[str, tuple[str, str]]:
    """key -> (class, note): the keys in sorted order, the classes in turn, each
    class's notes in turn within it. Deterministic, so both sides of a
    before/after pair see the same notes on the same rows.

    Refused when there is no row (`notes_corpus_no_rows`), and when there are
    fewer rows than classes (`notes_corpus_classes_unplaced`): section 2 asks
    for a row per class, and a class landing on no row would be in the corpus
    and in no payload, unremarked."""
    ordered = sorted(keys)
    if not ordered:
        raise Refused("notes_corpus_no_rows", "The assessment has no answer row to write notes to.")
    n = len(corpus.classes)
    if len(ordered) < n:
        raise Refused(
            "notes_corpus_classes_unplaced",
            f"The corpus has {n} classes and the assessment {len(ordered)} rows: "
            "some class would land on no row.",
        )
    out: dict[str, tuple[str, str]] = {}
    for i, key in enumerate(ordered):
        cls, notes = corpus.classes[i % n]
        out[key] = (cls, notes[(i // n) % len(notes)])
    return out


def _write_corpus_notes(
    db: Any, rows: Mapping[str, Any], corpus: NotesCorpus, client_name: str | None
) -> tuple[dict[str, str], int]:
    """Write the corpus's notes over `rows` (key -> an answer row with a
    `notes` column) and commit, in the throwaway database every `measure_*`
    has already checked it is bound to. Returns key -> class and the number of
    placeholders filled. Nothing else on a row is touched."""
    _require_client_name(
        [n for _, notes in corpus.classes for n in notes], client_name, "--notes-corpus"
    )
    assigned = assign_notes(list(rows), corpus)
    filled = 0
    for key, (_, note) in assigned.items():
        rows[key].notes, k = _fill_client_name(note, client_name)
        filled += k
    db.commit()
    _log.info(
        "measure_ai_consistency.notes_corpus_written",
        corpus=corpus.corpus,
        rows=len(assigned),
        client_name_substituted=filled,
    )
    return {key: cls for key, (cls, _) in assigned.items()}, filled


def _corpus_setup(
    corpus: NotesCorpus, classes_by_key: Mapping[str, str], sent: Any, filled: int
) -> dict:
    """The report's record of the corpus run: per class, the rows it landed
    on and how many of them the route's builder actually SENT (csf_score sends
    only answers "with actual signal", so a blank note on an unscored row is
    written and not sent). Refused when the builder sent none at all
    (`notes_corpus_nothing_sent`): that run would measure no corpus text."""
    sent_keys = set(sent)
    per_class = {
        cls: {
            "rows": sum(1 for c in classes_by_key.values() if c == cls),
            "sent": sum(1 for k, c in classes_by_key.items() if c == cls and k in sent_keys),
        }
        for cls, _ in corpus.classes
    }
    if not any(v["sent"] for v in per_class.values()):
        raise Refused(
            "notes_corpus_nothing_sent",
            "The route's builder sent none of the rows the corpus was written to.",
        )
    return {
        "corpus": corpus.corpus,
        "sha256": corpus.sha256,
        "rows": len(classes_by_key),
        "classes": per_class,
        "client_name_substituted": filled,
    }


def preflight(*, database_url: str, llm_mode: str, redaction_mode: str) -> None:
    """Refuse unless this is a throwaway SQLite database, live mode and strict
    redaction. Each refusal names its own cause."""
    if not database_url.startswith("sqlite"):
        raise Refused(
            "database_not_sqlite",
            "DATABASE_URL must be a SQLite file: a measurement writes llm_calls rows "
            "and must never reach a shared database.",
        )
    if llm_mode != "live":
        raise Refused(
            "llm_mode_not_live",
            f"SHIELD_LLM_MODE is {llm_mode!r}; a measurement needs live mode "
            "(fixture responses agree with themselves by construction).",
        )
    if redaction_mode != "strict":
        raise Refused(
            "redaction_not_strict",
            f"SHIELD_REDACTION_MODE is {redaction_mode!r}; a measurement runs only "
            "with strict redaction.",
        )


def _job_shape(job: str) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    """(list key, key fields, compared fields) for `job`. zt_score's are the
    route's own constants, imported rather than restated, so the measure
    compares exactly the fields the apply path reads."""
    if job == "zt_score":
        from app.routes.zt import _ROW_KEY_FIELDS, _ZT_ROW_FIELDS

        return "capabilities", _ROW_KEY_FIELDS, _ZT_ROW_FIELDS
    if job == "csf_score":
        # `what_we_found` is the route's sixth run field and is not compared:
        # free text differs in wording on every run.
        from app.routes.csf import _DIM_FIELDS
        from app.routes.csf import _ROW_KEY_FIELDS as _CSF_KEY_FIELDS

        return "scores", _CSF_KEY_FIELDS, _DIM_FIELDS
    if job == "mitre_map":
        # The run's own diff fields (`routes/attack.py::_DIFF_FIELDS`), less the
        # free text -- imported, so a field the apply path gains is compared.
        from app.routes.attack import _DIFF_FIELDS

        fields = tuple(f for f in _DIFF_FIELDS if f not in _ATTACK_FREE_TEXT)
        return "techniques", ("technique_code",), fields
    if job == "tech_debt_extract":
        # The parser's own record (`ExtractedCapability`), less the key and the
        # free text: what the extraction would STORE, after its coercion.
        from dataclasses import fields as dc_fields

        from app.tech_debt.extract import ExtractedCapability

        names = tuple(
            f.name
            for f in dc_fields(ExtractedCapability)
            if f.name != "source_row_index"
            and f.name not in _TECH_DEBT_FREE_TEXT
            and f.name not in _TECH_DEBT_NOT_JUDGEMENTS
        )
        return "items", ("source_row_index",), names
    raise Refused("job_not_implemented", f"{job!r} has no measure yet; see the module docstring.")


#: Per job, the compared fields that hold a LIST. Compared as sets: the order a
#: model lists tools in is not a judgement, so ["A", "B"] and ["B", "A"] agree.
_LIST_FIELDS: dict[str, tuple[str, ...]] = {
    "mitre_map": ("detection_tools", "prevention_tools", "response_tools"),
    "tech_debt_extract": ("security_functions",),
}


def _str_set(v: Any) -> frozenset[str] | None:
    """`v` as a set of strings, or None when it is not a list of strings."""
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        return None
    return frozenset(v)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """|a & b| / |a | b|, for a NON-EMPTY union only. Two empty lists are not
    agreement about anything: counted as absent by the caller, so a prompt
    that cites fewer tools cannot score as more consistent."""
    union = a | b
    if not union:
        raise ValueError("the Jaccard of two empty sets is not a measure of agreement")
    return len(a & b) / len(union)


#: Jobs whose route-side merge keeps only JSON objects (`_run_mitre_map_batched`,
#: and the extraction's `_parse_response`), so a non-object row never reaches
#: `compare_pair` and an `unreadable` count would be a constant 0. They report
#: `unreadable` as None ("not observable here") instead, and a row whose key is
#: null -- `source_row_index` the parser could not convert, or no
#: `technique_code` -- is `unkeyable`: excluded, counted, never compared with
#: another run's unkeyable row under the shared key "null".
_OBJECTS_ONLY_UPSTREAM = ("mitre_map", "tech_debt_extract")


def _is_whole(v: Any) -> bool:
    """A JSON integer. `True` is an int in Python and is not one here."""
    return type(v) is int


def _same(a: Any, b: Any) -> bool:
    """Equal AND of the same JSON type, so `true` never matches `1`."""
    return type(a) is type(b) and a == b


@dataclass(frozen=True)
class AttackScope:
    """What the mitre_map APPLY path checks a suggestion against
    (`routes/attack.py`): the assessment's technique codes -- a code outside
    them finds no row and is skipped (`row is None`) -- and the run's
    `CitationResolver`. `resolver=None` compares tool lists as sent."""

    resolver: Any
    assessment_codes: frozenset[str]


@dataclass(frozen=True)
class ZtScope:
    """What the zt_score APPLY path (`routes/zt.py::_zt_run_work`) checks a
    suggestion against: the framework's top stage (`_validated_stage`'s range)
    and the assessment's capability codes -- a code outside them finds no row
    and is dropped as `unknown_key` (#867 re-review F1).

    `framework` (a catalog `ZtFrameworkCode`) is what `_zt_capability_max`
    reads each capability's own maximum from, as the apply path does
    (`target_caps.max_stage_for`, #839 F1). `None` checks the ladder only,
    and only a scope built by hand does that: `measure_zt` always passes the
    assessment's framework."""

    max_stage: int
    codes: frozenset[str]
    framework: Any = None


@dataclass(frozen=True)
class CsfScope:
    """What the csf_score APPLY path (`routes/csf.py::_apply_suggestions`)
    checks an entry against: the assessment's "tier|subcategory_code" row keys
    -- a key outside them is dropped as `unknown_key` (#867 re-review F1). An
    entry its batch was not asked for (`not_in_batch`) is split out before the
    comparison, by the route's own `_split_strays` (`csf_run_data`)."""

    row_keys: frozenset[str]


def _require_context(job: str, context: Any) -> None:
    """Refuse a comparison the apply path's refusals cannot be judged in. A
    missing context is "could not look", and must never share a branch with
    "nothing refused" (CLAUDE.md: the silent-success branch)."""
    if job == "mitre_map" and not isinstance(context, AttackScope):
        raise TypeError(
            "mitre_map needs an AttackScope: whether a suggestion is refused depends "
            f"on the assessment's codes; got {type(context).__name__}."
        )
    if job == "zt_score" and not isinstance(context, ZtScope):
        raise TypeError(
            "zt_score needs a ZtScope: the apply path refuses a stage off the ladder "
            f"and a code the assessment lacks; got {type(context).__name__}."
        )
    if job == "csf_score" and not isinstance(context, CsfScope):
        raise TypeError(
            "csf_score needs a CsfScope: the apply path refuses a row key the "
            f"assessment lacks; got {type(context).__name__}."
        )


def _index(
    rows: Sequence[Any], key_fields: tuple[str, ...], *, unkeyable: list[int] | None = None
) -> tuple[dict, int, int]:
    """Rows by key. A non-object row is unreadable; a key seen twice is ambiguous
    and indexes neither copy. Returns (index, unreadable, extra copies of a
    repeated key). With `unkeyable` given, a row whose key fields are all null
    is excluded and counted into it instead of being indexed under "null"."""
    seen: dict[tuple, Any] = {}
    dupes: set[tuple] = set()
    unreadable = extra_copies = 0
    for row in rows:
        if not isinstance(row, dict):
            unreadable += 1
            continue
        if unkeyable is not None and all(row.get(f) is None for f in key_fields):
            unkeyable.append(1)
            continue
        key = tuple(json.dumps(row.get(f), sort_keys=True) for f in key_fields)
        if key in seen or key in dupes:
            dupes.add(key)
            extra_copies += 1
        seen[key] = row
    for key in dupes:
        seen.pop(key, None)
    return seen, unreadable, extra_copies


@functools.lru_cache(maxsize=1)
def _tech_debt_name_sentinel() -> str:
    """The name the extraction's parser INVENTS for an item the model sent no
    name for -- read from the parser by parsing exactly that, never restated
    here, so a change to the sentinel cannot leave this behind."""
    from app.tech_debt.extract import _parse_response

    return _parse_response('{"items": [{"source_row_index": 0}]}')[0].name


#: Per job, field -> a value the PARSER puts there when the model gave nothing.
_PARSER_SENTINELS: dict[str, dict[str, Callable[[], Any]]] = {
    "tech_debt_extract": {"name": _tech_debt_name_sentinel},
}


def _attack_row_refused(row: Mapping[str, Any], scope: AttackScope) -> bool:
    """Would the mitre_map APPLY path write NOTHING from this suggestion? In the
    route's own order (`routes/attack.py`, the run's apply loop):

    1. a code the assessment does not hold: `rows.get(code)` is None, skipped;
    2. a computed parent: `is_computed_parent`, `parent_suggestions_refused`;
    3. a status outside `_AI_WRITABLE_STATUSES`: `statuses_rejected`;
    4. an offered reason `is_valid_reason` rejects for it: `reason_codes_rejected`.

    Steps 1-2 are `_key_refused`, shared with the other jobs. Steps 2-4 CALL
    the catalog's, the route's and the vocabulary's predicates; step 1 is
    membership in the codes the apply path indexes (`AttackScope.
    assessment_codes`, built from the same `req.rows`). Locked and
    concurrently edited rows are skipped too, and are NOT modelled here: they
    are consultant state, not the model's answer (`attack_downstream`)."""
    from app.attack.coverage import is_valid_reason
    from app.routes.attack import _AI_WRITABLE_STATUSES

    if _key_refused("mitre_map", row, scope):
        return True
    st = row.get("status")
    if not (isinstance(st, str) and st in _AI_WRITABLE_STATUSES):
        return True
    offered = row.get("reason_code")
    return offered is not None and not (isinstance(offered, str) and is_valid_reason(st, offered))


#: The key the measure gives an entry `routes/csf.py::_split_strays` drops
#: as `not_in_batch` when no batch that asked for the row answered it: the run
#: named the row and the apply path writes nothing to it (`csf_run_data`).
_NOT_IN_BATCH = "__measure_not_in_batch__"


def _csf_key(row: Mapping[str, Any]) -> str:
    """The row key as `routes/csf.py::_apply_suggestions` builds it."""
    return f"{row.get('tier')}|{row.get('subcategory_code')}"


def _zt_capability_max(field: str, row: Mapping[str, Any], context: Any) -> int | None:
    """The `capability_max` `_zt_run_work` passes `_validated_stage` for this
    row and field: the capability's own maximum for a maturity (`current`)
    stage, None for a target (#839 F1, the #867 hand-off). Derived by the same
    `max_stage_for`, never a copy of its table."""
    code = row.get("code")
    if field != "current" or context.framework is None or not isinstance(code, str):
        return None
    from app.zt.target_caps import max_stage_for

    return max_stage_for(context.framework, code)


def _key_refused(job: str, row: Mapping[str, Any], context: Any) -> bool:
    """Would the apply path drop this answer by its KEY, before reading any
    value? The FIRST refusal on each path (#867 re-review F1, B-1's twin):

    * zt_score: `rows.get(code)` is None (`unknown_key`);
    * csf_score: `rows.get("tier|subcategory_code")` is None (`unknown_key`),
      or the entry was answered only out of its batch (`not_in_batch`);
    * mitre_map: no row for the code, or a computed parent
      (`_attack_row_refused` steps 1-2).

    Membership in the keys the apply path indexes (the scope, built from the
    same `req.rows`); `is_computed_parent` is called. Locked, protected and
    concurrently edited rows are consultant state and are not modelled."""
    if job == "zt_score":
        code = row.get("code")
        return not (isinstance(code, str) and code in context.codes)
    if job == "csf_score":
        return bool(row.get(_NOT_IN_BATCH)) or _csf_key(row) not in context.row_keys
    if job == "mitre_map":
        from app.attack.parents import is_computed_parent

        code = row.get("technique_code")
        if not (isinstance(code, str) and code in context.assessment_codes):
            return True
        return is_computed_parent(code)
    return False


def _resolved_tools(value: Any, resolver: Any) -> list[str] | None:
    """A cited tool list as the run would STORE it: resolved by the run's own
    `CitationResolver`, unknown names dropped. None when it is not a list."""
    from app.attack.citations import resolve_citations

    if not isinstance(value, list):
        return None
    return list(resolve_citations(value, resolver).tools)


def _absence(job: str, field: str, row: Mapping[str, Any], context: Any = None) -> str | None:
    """How `field` is ABSENT from `row`, or None when it holds an answer.

    THE ABSENCE MATRIX (#867, after rounds of "less extracted reads as more
    consistent" found one form at a time). The forms a value takes when a run
    gave no USABLE answer:

    | form       | where it arises                                              |
    | ---------- | ------------------------------------------------------------ |
    | missing    | any job, any field: the model omitted the key                |
    | null       | any scalar; the extraction's refused values become null (#878) |
    | empty      | list fields: the tool lists, `security_functions`            |
    | sentinel   | tech_debt `name`: the parser invents one when none was sent  |
    | refused    | any keyed job, FIRST: the apply path drops the answer by its |
    |            | key (`_key_refused`: an unknown zt code or csf row key, a    |
    |            | csf entry answered only out of its batch, a mitre_map code   |
    |            | with no row or a computed parent), whatever the field holds. |
    |            | mitre_map: the apply path writes nothing from the suggestion |
    |            | (`_attack_row_refused`: a code the assessment lacks, a       |
    |            | computed parent, a status it may not write, a mispaired      |
    |            | reason), and a tool list none of whose names the run's       |
    |            | resolver can place. csf_score: `routes/csf.py::              |
    |            | _validated_dimension` refuses it (unparseable, outside 0-2,  |
    |            | not whole). zt_score: `routes/zt.py::_validated_stage`       |
    |            | refuses it (unparseable, off the 1..max_stage ladder, not    |
    |            | whole, or a maturity stage above the capability's own        |
    |            | maximum). The tech_debt extraction's refusals arrive as null.|

    Every value refusal above is the apply path's own function, CALLED (#867
    review B-1, B-4); a key refusal is membership in the keys the apply path
    indexes (#867 re-review F1). Key refusal comes first, so a refused row's
    omitted field is `refused`, not `missing`.

    ONE rule for all of them, in `compare_pair`: the pair is COMPARED, adds
    NOTHING to any agreement figure, and is counted in `both_absent` /
    `one_absent`. A list field holding a non-list is not an absence but a
    malformed answer, counted as `not_a_list` under the same rule.

    `context` is the job's `_require_context`: an `AttackScope` for mitre_map,
    a `ZtScope` for zt_score, a `CsfScope` for csf_score.
    """
    if _key_refused(job, row, context):
        return "refused"
    if field not in row:
        return "missing"
    value = row[field]
    if value is None:
        return "null"
    if job == "mitre_map" and _attack_row_refused(row, context):
        return "refused"
    if job == "csf_score":
        # The apply path's own validator, called (#867): unparseable, outside
        # 0-2, or not whole is refused there, so it is no answer here.
        from app.routes.csf import _validated_dimension

        if _validated_dimension(value)[1] is not None:
            return "refused"
    if job == "zt_score":
        # The apply path's own validator, called (#867 review B-4): parse,
        # range 1..max_stage, wholeness, then the capability's own maximum
        # for a maturity stage, as `_zt_run_work` judges them.
        from app.routes.zt import _validated_stage

        cap = _zt_capability_max(field, row, context)
        if _validated_stage(value, context.max_stage, cap)[1] is not None:
            return "refused"
    if field in _LIST_FIELDS.get(job, ()) and isinstance(value, list):
        if not value:
            return "empty"
        resolver = context.resolver if job == "mitre_map" else None
        if resolver is not None and not _resolved_tools(value, resolver):
            return "refused"
    sentinel = _PARSER_SENTINELS.get(job, {}).get(field)
    if sentinel is not None and value == sentinel():
        return "sentinel"
    return None


def compare_pair(
    job: str, a: Mapping[str, Any], b: Mapping[str, Any], *, context: Any = None
) -> dict:
    """Agreement between two parsed responses: row set, then per field over the
    rows present in both. Every count is a denominator or a numerator of one.

    `compared` is EVERY row in both runs, for every field. A pair where either
    side is absent (`_absence`) or a list field is malformed is compared and
    adds nothing to `equal`, `within_one`, `mean_abs_diff` or the Jaccard -- so
    a run that answers LESS can never read as more consistent. Values are
    compared as the apply path would STORE them: csf_score's dimensions through
    `_validated_dimension`, zt_score's stages through `_validated_stage`, so "2"
    and 2 agree; mitre_map's tool lists resolved by `context.resolver` when it
    has one. `context` is required where `_require_context` says so."""
    _require_context(job, context)
    list_key, key_fields, fields = _job_shape(job)
    objects_only = job in _OBJECTS_ONLY_UPSTREAM
    keyless_a: list[int] | None = [] if objects_only else None
    keyless_b: list[int] | None = [] if objects_only else None
    ia, unread_a, dup_a = _index(a.get(list_key) or [], key_fields, unkeyable=keyless_a)
    ib, unread_b, dup_b = _index(b.get(list_key) or [], key_fields, unkeyable=keyless_b)
    both = sorted(set(ia) & set(ib))
    list_fields = _LIST_FIELDS.get(job, ())
    out_fields: dict[str, dict] = {}
    for f in fields:
        compared = equal = within_one = missing_a = missing_b = not_a_list = 0
        both_absent = one_absent = 0
        diffs: list[int] = []
        jaccards: list[float] = []
        for k in both:
            ra, rb = ia[k], ib[k]
            # Every row in both runs is compared, for every field: a key one
            # run omitted is a disagreement, never a row taken out of the
            # denominator (#867 narrow review at b544311b, B2).
            compared += 1
            gone_a = _absence(job, f, ra, context)
            gone_b = _absence(job, f, rb, context)
            # A key the apply path refuses is `refused`, not a missing field.
            missing_a += int(gone_a == "missing")
            missing_b += int(gone_b == "missing")
            if gone_a and gone_b:
                both_absent += 1
                continue
            if gone_a or gone_b:
                one_absent += 1
                continue
            va, vb = ra[f], rb[f]
            if f in list_fields and job == "mitre_map" and context.resolver is not None:
                va = _resolved_tools(va, context.resolver)
                vb = _resolved_tools(vb, context.resolver)
            if job == "csf_score":
                # Compared as stored: "2" and 2 are the same applied score.
                from app.routes.csf import _validated_dimension

                va, vb = _validated_dimension(va)[0], _validated_dimension(vb)[0]
            if job == "zt_score":
                # Compared as stored, the twin of csf_score's line above (#867
                # review B-5): "2" and 2 are the same applied stage.
                from app.routes.zt import _validated_stage

                # No capability maximum here: `_absence` has already refused
                # a maturity stage above it, so none reaches this line.
                va = _validated_stage(va, context.max_stage)[0]
                vb = _validated_stage(vb, context.max_stage)[0]
            if f in list_fields:
                sa, sb = _str_set(va), _str_set(vb)
                if sa is None or sb is None:
                    # A bare string, a list holding a number: not the shape
                    # asked for. Counted, never coerced into a set it was not,
                    # and no agreement.
                    not_a_list += 1
                    continue
                jaccards.append(_jaccard(sa, sb))
                equal += int(sa == sb)
                continue
            if _same(va, vb):
                equal += 1
            if _is_whole(va) and _is_whole(vb):
                diffs.append(abs(va - vb))
                if abs(va - vb) <= 1:
                    within_one += 1
        out_fields[f] = {
            "compared": compared,
            "equal": equal,
            "within_one": within_one,
            # Over the pairs where both runs gave a whole number (P1, filed):
            # a distance between an answer and no answer is not defined.
            "mean_abs_diff": (sum(diffs) / len(diffs)) if diffs else None,
            "missing_in_a": missing_a,
            "missing_in_b": missing_b,
            # The absence matrix (`_absence`): compared, no agreement.
            "both_absent": both_absent,
            "one_absent": one_absent,
        }
        if f in list_fields:
            # compared == judged + both_absent + one_absent + not_a_list, and
            # the Jaccard divides by `compared`: only `judged` pairs add to it.
            out_fields[f]["judged"] = len(jaccards)
            out_fields[f]["not_a_list"] = not_a_list
            out_fields[f]["mean_jaccard"] = (sum(jaccards) / compared) if compared else None
    rows: dict[str, Any] = {
        "in_both": len(both),
        "only_in_a": len(set(ia) - set(ib)),
        "only_in_b": len(set(ib) - set(ia)),
        # None, not 0, where the route's own merge already dropped non-objects:
        # this count cannot see them (`_OBJECTS_ONLY_UPSTREAM`).
        "unreadable_a": None if objects_only else unread_a,
        "unreadable_b": None if objects_only else unread_b,
        "duplicate_keys_a": dup_a,
        "duplicate_keys_b": dup_b,
    }
    if objects_only:
        rows["unkeyable_a"] = len(keyless_a or [])
        rows["unkeyable_b"] = len(keyless_b or [])
    return {"rows": rows, "fields": out_fields}


def _zt_sent_current(inputs: Mapping[str, Any], code: Any) -> Any:
    answer = (inputs.get("answers") or {}).get(code) if isinstance(code, str) else None
    return answer.get("current") if isinstance(answer, dict) else None


#: Per job, the compared fields whose value the payload already SENDS, and how
#: to read the sent value for a row. Agreement on such a field can be the model
#: repeating its input on both runs rather than judging twice; `echo_share`
#: says how much. zt_score sends each capability's stored `current` and no
#: target (`routes/zt.py::_zt_ai_request_for`).
_ECHO_FIELDS: dict[str, dict[str, Any]] = {
    "zt_score": {"current": _zt_sent_current},
}


def echo_share(
    job: str, inputs: Mapping[str, Any], data: Mapping[str, Any], *, context: Any
) -> dict:
    """For one run: of the rows where something was sent AND the model gave a
    USABLE answer, how many answers equal (same JSON type) what was sent. A row
    with no usable answer -- the field omitted, null, or refused by the apply
    path, its key included (`_absence`, the one rule `compare_pair` uses) -- is
    `absent`, never an answer that moved off what was sent: before #867
    re-review F2 a run answering null everywhere read as "never just an echo".
    A usable answer for a row sent nothing is `nothing_sent`, since there was
    nothing to repeat."""
    _require_context(job, context)
    list_key, key_fields, _ = _job_shape(job)
    out: dict[str, dict[str, int]] = {}
    for field, sent_value in _ECHO_FIELDS.get(job, {}).items():
        answered = echoed = nothing_sent = absent = 0
        for row in data.get(list_key) or []:
            if not isinstance(row, dict):
                continue
            # Absence FIRST: a row the apply path refuses (an unknown code
            # included, which was sent nothing) is no answer at all.
            if _absence(job, field, row, context) is not None:
                absent += 1
                continue
            sent = sent_value(inputs, row.get(key_fields[0]))
            if sent is None:
                nothing_sent += 1
                continue
            answered += 1
            # Raw, NOT through `_validated_stage`, deliberately: this asks
            # whether the model REPEATED its input, and "2" for a sent 2 is a
            # different string than it was sent. The agreement figures compare
            # stored values (`compare_pair`); this one does not.
            if _same(sent, row[field]):
                echoed += 1
        out[field] = {
            "sent_and_answered": answered,
            "echoed": echoed,
            "nothing_sent": nothing_sent,
            "absent": absent,
        }
    return out


def zt_downstream(framework: Any, *, engagement_stage: int, data: Mapping[str, Any]) -> dict:
    """The gaps a client would see if every value in `data` were applied,
    counted by the engine (`analyze_gaps`) with no truncation.

    Only whole-number stages are passed on; anything else is counted in
    `non_integer_values` and treated as absent, because the engine's own
    validator calls `int()`, which would read `true` as 1 and `"2"` as 2.
    A whole number outside the framework's stages is passed on (the engine
    treats it as unscored, or an unusable target) and ALSO counted in
    `out_of_range_values`, so a run of stage 9s cannot read as a run that
    simply left rows blank. `unusable_target_codes` is the engine's own list.
    Rows the real apply path would skip (locked, protected, edited) are not
    modelled: this is what the model ASKED for, not what a run would write.

    A TWIN LEFT ALONE, on purpose (#867 review B-4/B-5): unlike `compare_pair`
    and `csf_levels`, this does NOT go through `routes/zt.py::_validated_stage`.
    It passes out-of-range whole numbers ON so the engine names unusable
    targets, which the validator would hide; and it reads "2" as non-integer
    where the apply path stores 2. The second is a known disagreement with the
    apply path, recorded on #867 for a decision rather than changed here.
    """
    from app.zt.catalog import capabilities
    from app.zt.maturity import level_count
    from app.zt.scoring import analyze_gaps

    max_stage = level_count(framework)
    out_of_range = 0

    answers: dict[str, int] = {}
    targets: dict[str, int] = {}
    non_integer = 0
    for row in data.get("capabilities") or []:
        if not isinstance(row, dict) or not isinstance(row.get("code"), str):
            continue
        for field, dest in (("current", answers), ("target", targets)):
            if field not in row or row[field] is None:
                continue
            if _is_whole(row[field]):
                dest[row["code"]] = row[field]
                if not 1 <= row[field] <= max_stage:
                    out_of_range += 1
            else:
                non_integer += 1
    gaps = analyze_gaps(
        framework,
        answers,
        targets=targets,
        target_stage=engagement_stage,
        top_n=len(capabilities(framework)),
    )
    return {
        "gap_codes": sorted(g.code for g in gaps.gaps),
        "total_gap_count": gaps.total_gap_count,
        "unscored_count": len(gaps.unscored_codes),
        "non_integer_values": non_integer,
        "out_of_range_values": out_of_range,
        "unusable_target_codes": sorted(gaps.unusable_target_codes),
    }


def csf_levels(data: Mapping[str, Any], *, has_evidence: Mapping[str, bool]) -> dict:
    """Each row's maturity level, by `csf.playbook.score_tier` -- the number a
    client sees per (tier, subcategory) -- keyed "tier|subcategory_code" as the
    route keys its rows.

    A row is scored only when the apply path would store all five of its
    dimensions: each goes through `routes/csf.py::_validated_dimension`, CALLED
    (#867 review B-3), so "2" and 2.0 score as 2, and 3, `true` or 1.5 make the
    row unscoreable rather than reaching the engine's `clamped()`, which would
    read them as 2, 1 and 1. `unscoreable_keys` names the assessment's rows the
    run ANSWERED and left unscoreable, so a pair can count them
    (`csf_level_agreement`); `not_scoreable` also counts entries naming no row
    of the assessment. `has_evidence` is the stored row's flag, as the route
    passes it."""
    from app.csf.playbook import DimensionScores, score_tier
    from app.routes.csf import _DIM_FIELDS, _validated_dimension

    levels: dict[str, int] = {}
    unscoreable: set[str] = set()
    not_scoreable = evidence_capped = 0
    for row in data.get("scores") or []:
        if not isinstance(row, dict):
            continue
        key = f"{row.get('tier')}|{row.get('subcategory_code')}"
        checked = [_validated_dimension(row.get(f)) for f in _DIM_FIELDS]
        if key not in has_evidence or any(reason is not None for _, reason in checked):
            not_scoreable += 1
            if key in has_evidence:
                unscoreable.add(key)
            continue
        dims = [value for value, _ in checked]
        result = score_tier(
            DimensionScores(**dict(zip(_DIM_FIELDS, dims, strict=True))),
            has_evidence=has_evidence[key],
        )
        levels[key] = result.level
        evidence_capped += int(result.evidence_capped)
    # `evidence_capped` counts the rows whose level the engine CAPPED for want of
    # evidence (CSF_Flow_Spec section 8: at most Level 2). Without it, a run that
    # scored every row L4 and one that scored every row L2 read as agreeing.
    return {
        "levels": levels,
        # A key answered twice, once scoreable, is in both: the pair rule below
        # then counts it as unscoreable, never as agreement.
        "unscoreable_keys": sorted(unscoreable),
        "not_scoreable": not_scoreable,
        "evidence_capped": evidence_capped,
    }


def csf_run_data(
    batch_inputs: Sequence[Mapping[str, Any]],
    answers: Sequence[Mapping[str, Any]],
    rows: Mapping[str, Any],
) -> dict:
    """One csf_score run's batches as the apply path would SEE them, split by
    the route's own `routes/csf.py::_split_strays` (#867 re-review F1):

    * entries to apply, in batch order, as `scores`;
    * an entry naming a real row its batch was not asked for is DROPPED there
      (`not_in_batch`). When a batch that asked for the row also answered it,
      that answer is the one applied, so the stray is simply left out here.
      When none did, the apply path writes nothing to a row the run named, so
      the row is kept as a key-only entry `_absence` reads as refused --
      compared, never agreement -- rather than vanishing from the denominator.

    `not_in_batch` counts every stray the route would drop."""
    from app.routes.csf import _split_strays

    scores, strays = _split_strays(list(batch_inputs), list(answers), rows)
    applied = {_csf_key(e) for e in scores if isinstance(e, dict)}
    marked: set[str] = set()
    for entry in strays:
        key = _csf_key(entry)
        if key in applied or key in marked:
            continue
        marked.add(key)
        # Key fields only: the stray's values are never compared or logged.
        scores.append(
            {
                "tier": entry.get("tier"),
                "subcategory_code": entry.get("subcategory_code"),
                _NOT_IN_BATCH: True,
            }
        )
    return {"scores": scores, "not_in_batch": len(strays)}


def csf_level_agreement(
    la: Mapping[str, Any], lb: Mapping[str, Any], has_evidence: Mapping[str, bool]
) -> dict:
    """Level agreement between two runs' `csf_levels`, under the absence rule
    (#867 review B-3): every row ANSWERED in both runs is compared; a row left
    unscoreable in EITHER adds nothing to `equal` and is counted in
    `one_unscoreable` / `both_unscoreable`, as `compare_pair` counts
    `one_absent` / `both_absent`. Intersecting the SCORED rows instead let a
    run that scored 10 of 100 rows read as 10 of 10 agreeing."""
    scored_a, scored_b = la["levels"], lb["levels"]
    gone_a = set(la["unscoreable_keys"])
    gone_b = set(lb["unscoreable_keys"])
    both = (set(scored_a) | gone_a) & (set(scored_b) | gone_b)
    lost_a = {k for k in both if k in gone_a or k not in scored_a}
    lost_b = {k for k in both if k in gone_b or k not in scored_b}
    judged = both - lost_a - lost_b
    return {
        "compared": len(both),
        "equal": sum(scored_a[k] == scored_b[k] for k in judged),
        "one_unscoreable": len(lost_a ^ lost_b),
        "both_unscoreable": len(lost_a & lost_b),
        # Rows with no evidence can never score above Level 2, so their
        # level agreement is agreement within a capped range.
        "no_evidence_rows": sum(1 for k in both if not has_evidence[k]),
    }


def run_loop(
    runs: int,
    one_run: Callable[[int], RunRecord],
    *,
    max_output_tokens: int | None,
    stop_on_failure: bool = False,
    max_usd: float | None = None,
    price: Mapping[str, float] | None = None,
    progress: Callable[[Sequence[RunRecord]], None] | None = None,
) -> list[RunRecord]:
    """Call `one_run(n)` for n = 1..runs. Once the output tokens spent exceed
    `max_output_tokens`, no further run STARTS; each one not started is recorded
    as failed (`stopped_output_budget`). A run already under way is never cut
    off, so the overrun is bounded by one run's output. A run whose spend is
    UNKNOWN (no output count, or a call with none) also stops the rest under a
    budget (`stopped_unknown_spend`): a budget that cannot be counted is not
    being kept. With `stop_on_failure`, no run starts after a failed one
    (`stopped_after_failure`): a rate-limited provider is not retried into.
    A run that hit the run deadline stops every later run, whatever else is
    set (`stopped_after_deadline`).

    THE DOLLAR GUARD (`max_usd`, #952 review F1): before each run after the
    first, the spend so far PLUS the largest single run so far -- input and
    output at list price (`run_usd`) -- must not exceed `max_usd`, or that run
    is not started (`stopped_budget`). It is a projection, not a promise: a run
    larger than every run before it can still cross the line, and THE FIRST
    RUN IS NOT BOUNDED AT ALL, because nothing is known before it. A run that
    that started no provider call spent nothing and stops nothing; one whose
    started calls are not all accounted for by rows is unknown spend.

    A run not started made no call, so its `charged_likely` is False (#952 F4).
    `progress`, when given, is called with every record after each one is
    added, so a caller can keep a report of every completed run on disk."""
    from app.ai.runs import RUN_DEADLINE_EXCEEDED

    if max_usd is not None and price is None:
        raise ValueError("a dollar guard needs the price it is counted in")
    records: list[RunRecord] = []
    spent = 0
    unknown = False
    spent_usd = 0.0
    largest_usd = 0.0

    def not_started(reason: str) -> RunRecord:
        return RunRecord(False, None, reason, 0, 0, charged_likely=False, calls=0, started=0)

    for n in range(1, runs + 1):
        if any(r.failure == RUN_DEADLINE_EXCEEDED for r in records):
            # A batch still inside a provider call after the deadline writes its
            # `llm_calls` row LATER, into whichever run is counting then. So no
            # run starts after a deadline, budget or not: its window would hold
            # a straggler's tokens under `tokens_complete: True`.
            records.append(not_started("stopped_after_deadline"))
        elif stop_on_failure and any(not r.ok for r in records):
            records.append(not_started("stopped_after_failure"))
        elif (max_output_tokens is not None or max_usd is not None) and unknown:
            _log.warning("measure_ai_consistency.budget_unknown_stop", run=n)
            records.append(not_started("stopped_unknown_spend"))
        elif max_output_tokens is not None and spent > max_output_tokens:
            _log.warning("measure_ai_consistency.budget_stop", run=n, output_tokens=spent)
            records.append(not_started("stopped_output_budget"))
        elif max_usd is not None and n > 1 and spent_usd + largest_usd > max_usd:
            _log.warning(
                "measure_ai_consistency.usd_budget_stop",
                run=n,
                spent_usd=spent_usd,
                largest_run_usd=largest_usd,
                max_usd=max_usd,
            )
            records.append(not_started("stopped_budget"))
        else:
            record = one_run(n)
            if not _spend_known(record):
                unknown = True
            spent += record.output_tokens or 0
            if price is not None and not unknown:
                usd = run_usd(record, price) or 0.0
                spent_usd += usd
                largest_usd = max(largest_usd, usd)
            records.append(record)
        if progress is not None:
            progress(records)
    return records


_NOT_STARTED = (
    "stopped_output_budget",
    "stopped_after_failure",
    "stopped_unknown_spend",
    "stopped_after_deadline",
    "stopped_budget",
)


def run_row(n: int, r: RunRecord, price: Mapping[str, float]) -> dict:
    """One run as the report's per-run record, counts and codes only."""
    return {
        "run": n,
        "ok": r.ok,
        "failure": r.failure,
        "cause": r.cause,
        "charged_likely": r.charged_likely,
        "input_tokens": r.input_tokens,
        "output_tokens": r.output_tokens,
        "tokens_complete": r.tokens_complete,
        "calls": r.calls,
        "calls_started": r.started,
        "estimated_usd": run_usd(r, price),
    }


def summarize(
    job: str,
    runs: Sequence[RunRecord],
    *,
    max_output_tokens: int | None = None,
    min_ok_runs: int = 2,
    context: Any = None,
    max_usd: float | None = None,
    price: Mapping[str, float] | None = None,
) -> dict:
    """Every pair of successful runs, plus the failed runs by number (1-based).
    Fewer than `min_ok_runs` successes is a failure: 2 for a measurement, since
    there is nothing to compare below that, and 1 for a cost probe. With
    `max_usd`, a `budget_usd` block reports the dollar guard's accounting."""
    ok = [(i + 1, r) for i, r in enumerate(runs) if r.ok]
    pairs = [
        {"pair": [i, j], **compare_pair(job, ra.data or {}, rb.data or {}, context=context)}
        for (i, ra), (j, rb) in itertools.combinations(ok, 2)
    ]
    failed = [
        {
            "run": i + 1,
            "failure": r.failure,
            "cause": r.cause,
            "charged_likely": r.charged_likely,
        }
        for i, r in enumerate(runs)
        if not r.ok
    ]
    # A run that called the provider and has no output count is spend nobody
    # can see. A budget-stopped run made no call, and neither did a run that
    # wrote no `llm_calls` row (#952 F3), so neither counts.
    called = [r for r in runs if r.failure not in _NOT_STARTED and r.started != 0]
    spent = sum(r.output_tokens or 0 for r in runs)
    report = {
        "job": job,
        "runs_requested": len(runs),
        "runs_ok": len(ok),
        "failed_runs": failed,
        "pairs": pairs,
        # Per run, so a cost is sized from one run's spend and a run that
        # could not count its own spend is named, not only folded into a total.
        "runs": [
            {
                "run": i + 1,
                "ok": r.ok,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "tokens_complete": r.tokens_complete,
            }
            for i, r in enumerate(runs)
        ],
        "tokens": {
            "input": sum(r.input_tokens or 0 for r in runs),
            "output": sum(r.output_tokens or 0 for r in runs),
            "complete": all(
                r.output_tokens is not None and r.tokens_complete and _spend_known(r)
                for r in called
            ),
        },
        "budget": {
            "max_output_tokens": max_output_tokens,
            "spent_output_tokens": spent,
            "overrun": max_output_tokens is not None and spent > max_output_tokens,
            # An overrun of False means nothing when the count is not complete.
            "complete": all(r.output_tokens is not None and r.tokens_complete for r in called),
        },
        "exit_code": 0 if not failed and len(ok) >= min_ok_runs else 1,
    }
    if max_usd is not None:
        if price is None:
            raise ValueError("a dollar budget needs the price it is counted in")
        per_run = [run_usd(r, price) for r in runs]
        spent_usd = round(sum(u for u in per_run if u is not None), 6)
        report["budget_usd"] = {
            "max_usd": max_usd,
            "spent_usd": spent_usd,
            "per_run_usd": per_run,
            "complete": all(u is not None for u in per_run),
            # Nothing is known before the first run, so nothing bounds it.
            "first_run_bounded": False,
            "overrun": spent_usd > max_usd,
        }
    return report


def _framework_enum(name: str) -> Any:
    from app.models.zt_assessment import ZtFramework

    return {"cisa": ZtFramework.CISA_ZTMM_2_0, "dod": ZtFramework.DOD_ZTRA}[name]


def _pick_assessment(
    db: Any, model: Any, status: Any, *, label: str, reopen_released: bool, **where: Any
) -> tuple[Any, str | None]:
    """The latest DRAFT/SUBMITTED `model` row matching `where`, or -- with
    `reopen_released`, and only when none is editable -- the latest RELEASED or
    APPROVED one set back to DRAFT. Returns (assessment, reopened_from).

    Why reopening exists: the demo seed releases its assessments, and every
    route builder refuses a locked one; a new version starts with empty answers.
    DRAFT is a state every assessment passed through before release. Never
    needed outside the throwaway database `preflight` insists on."""
    from sqlalchemy import select

    def latest(statuses: list[Any]) -> Any:
        q = select(model).where(model.status.in_(statuses))
        for column, value in where.items():
            q = q.where(getattr(model, column) == value)
        return db.execute(q.order_by(model.created_at.desc())).scalars().first()

    # ATT&CK has no SUBMITTED state; CSF and ZT do.
    editable = [s for s in (status.DRAFT, getattr(status, "SUBMITTED", None)) if s is not None]
    a = latest(editable)
    reopened_from = None
    if a is None and reopen_released:
        a = latest([status.RELEASED, status.APPROVED])
        if a is not None:
            reopened_from = a.status.value
            a.status = status.DRAFT
            db.commit()
            _log.info(
                "measure_ai_consistency.reopened",
                assessment_id=str(a.id),
                reopened_from=reopened_from,
            )
    if a is None:
        raise Refused(
            "no_editable_assessment",
            f"No draft or submitted {label} assessment"
            + ("" if reopen_released else " (--reopen-released was not given)")
            + ".",
        )
    return a, reopened_from


#: Every `measure_*` calls `_require_sqlite_bind` FIRST, before reading
#: anything: a measurement writes `llm_calls` rows, may reopen an assessment and
#: may seed a Working Profile, and each of those writes is then covered by the
#: one check rather than by a check beside each.
def _session_dialect(db: Any) -> str:
    return db.get_bind().dialect.name


def _require_sqlite_bind(db: Any, what: str) -> None:
    """A second, local check before any state change: `preflight` reads the
    settings, this reads the session actually in hand."""
    dialect = _session_dialect(db)
    if dialect != "sqlite":
        raise Refused(
            "state_change_needs_sqlite",
            f"Refusing {what}: the session is bound to {dialect!r}, not SQLite.",
        )


def _admin_user(db: Any) -> Any:
    """The requester recorded on each call. Checked BEFORE any state change."""
    from sqlalchemy import select

    from app.models.user import User, UserRole

    admin = (
        db.execute(select(User).where(User.role == UserRole.ADMIN).order_by(User.created_at))
        .scalars()
        .first()
    )
    if admin is None:
        raise Refused("no_admin_user", "No admin user to record as the requester.")
    return admin


def _client_of(db: Any, a: Any) -> Any:
    from app.models.client import Client
    from app.models.service import Service

    return db.get(Client, db.get(Service, a.service_id).client_id)


def _builder_refusal(exc: Exception) -> Refused:
    """A route builder's typed refusal (locked, not seeded), as a Refused."""
    detail = getattr(exc, "detail", None)
    text = detail.get("message") if isinstance(detail, dict) else detail
    return Refused("builder_refused", f"The route's payload builder refused: {text}")


def _failure(exc: Exception) -> tuple[str, str | None, bool | None]:
    """(reason, cause, charged_likely) for a failed run. The reason is typed;
    the cause is the underlying exception's TYPE name. Never a message, which
    can quote the model."""
    detail = getattr(exc, "detail", None)
    detail = detail if isinstance(detail, dict) else {}
    if detail.get("reason"):
        reason = str(detail["reason"])
    elif isinstance(getattr(exc, "reason", None), str):
        reason = exc.reason  # type: ignore[attr-defined]
    else:
        reason = type(exc).__name__
    cause = type(exc.__cause__).__name__ if exc.__cause__ is not None else None
    charged = detail.get("charged_likely")
    return reason, cause, charged if isinstance(charged, bool) else None


def _ok_runs(records: Sequence[RunRecord]) -> list[tuple[int, dict]]:
    return [(i + 1, r.data) for i, r in enumerate(records) if r.ok and r.data is not None]


def measure_zt(
    db: Any,
    llm: Any,
    *,
    framework: str,
    runs: int,
    reopen_released: bool = False,
    max_output_tokens: int | None = None,
    stop_on_failure: bool = False,
    notes_corpus: NotesCorpus | None = None,
    max_usd: float | None = None,
    price: Mapping[str, float] | None = None,
    progress: Callable[[Sequence[RunRecord]], None] | None = None,
) -> dict:
    """Run zt_score `runs` times on the latest editable assessment for
    `framework` and summarize. Writes only what `run_job` itself writes, plus
    the status change `reopen_released` asks for (see `_pick_assessment`) and,
    with `notes_corpus`, the corpus's notes over the rows the route's builder
    selects (`_write_corpus_notes`), before the payload is built from them."""
    from fastapi import HTTPException

    from app.ai.engine import run_job
    from app.ai.failures import ai_call_boundary
    from app.models.zt_assessment import ZtAssessment, ZtAssessmentStatus
    from app.routes.zt import _to_catalog_framework, _zt_ai_request_for
    from app.services.engagement_targets import client_target_stage
    from app.zt.scoring import resolve_target_stage

    _require_sqlite_bind(db, "a zt_score measurement")
    admin = _admin_user(db)
    a, reopened_from = _pick_assessment(
        db,
        ZtAssessment,
        ZtAssessmentStatus,
        label=framework,
        reopen_released=reopen_released,
        framework=_framework_enum(framework),
    )
    client = _client_of(db, a)
    try:
        req = _zt_ai_request_for(db, a, client)
    except HTTPException as exc:
        raise _builder_refusal(exc) from exc
    corpus_setup = None
    if notes_corpus is not None:
        # The builder's own rows, then the builder again over the new notes:
        # the payload is still built by the route, never assembled here.
        classes, filled = _write_corpus_notes(db, req.rows, notes_corpus, client.legal_name)
        req = _zt_ai_request_for(db, a, client)
        corpus_setup = _corpus_setup(
            notes_corpus, classes, req.preview.inputs.get("answers") or {}, filled
        )
    fw = _to_catalog_framework(a.framework)
    stage, stage_source = resolve_target_stage(fw, client_target_stage(db, a.service_id))
    _log.info(
        "measure_ai_consistency.start",
        job="zt_score",
        assessment_id=str(a.id),
        capabilities=len(req.rows),
        engagement_stage=stage,
        engagement_stage_source=stage_source,
        provider=llm.provider.name,
        model=llm.provider.model,
        runs=runs,
    )

    started_calls = _InvokeCounter(llm)

    def one_run(n: int) -> RunRecord:
        before = _call_ids(db)
        started_before = started_calls.n
        try:
            with ai_call_boundary(db, llm, purpose=req.preview.job_name):
                result = run_job(
                    db,
                    llm,
                    req.preview.job_name,
                    inputs=req.preview.inputs,
                    requested_by=admin.id,
                    service_id=a.service_id,
                    client_id=client.id,
                    client_org_name=req.preview.client_org_name,
                    name_hints=req.preview.name_hints,
                )
        except HTTPException as exc:
            reason, cause, typed = _failure(exc)
            tokens_in, tokens_out, complete = _tokens_since(db, before)
            calls = _calls_since(db, before)
            charged = _charged_likely(db, before, answered=0, typed=typed)
            _log.error(
                "measure_ai_consistency.run_failed",
                run=n,
                failure=reason,
                cause=cause,
                charged_likely=charged,
            )
            return RunRecord(
                False,
                None,
                reason,
                tokens_in,
                tokens_out,
                cause,
                charged,
                complete,
                calls=calls,
                started=started_calls.n - started_before,
            )
        db.commit()
        tokens_in, tokens_out, complete = _tokens_since(db, before)
        calls = _calls_since(db, before)
        _log.info(
            "measure_ai_consistency.run_ok",
            run=n,
            input_tokens=tokens_in,
            output_tokens=tokens_out,
            duration_ms=result.llm_call.duration_ms,
        )
        return RunRecord(
            True,
            result.data,
            None,
            tokens_in,
            tokens_out,
            tokens_complete=complete,
            calls=calls,
            started=started_calls.n - started_before,
        )

    records = run_loop(
        runs,
        one_run,
        max_output_tokens=max_output_tokens,
        stop_on_failure=stop_on_failure,
        max_usd=max_usd,
        price=price,
        progress=progress,
    )
    scope = ZtScope(max_stage=req.max_stage, codes=frozenset(req.rows), framework=fw)
    report = summarize(
        "zt_score",
        records,
        max_output_tokens=max_output_tokens,
        context=scope,
        max_usd=max_usd,
        price=price,
    )
    report["assessment_id"] = str(a.id)
    report["assessment_capabilities"] = len(req.rows)
    report["engagement_stage"] = {"stage": stage, "source": stage_source}
    report["input_setup"] = {"reopened_from": reopened_from}
    if corpus_setup is not None:
        report["input_setup"]["notes_corpus"] = corpus_setup
    report["provider"] = {"name": llm.provider.name, "model": llm.provider.model}
    report["echo"] = [
        {"run": n, **echo_share("zt_score", req.preview.inputs, data, context=scope)}
        for n, data in _ok_runs(records)
    ]
    report["downstream"] = [
        {"run": n, **zt_downstream(fw, engagement_stage=stage, data=data)}
        for n, data in _ok_runs(records)
    ]
    return report


class _InvokeCounter:
    """Counts `LLMClient.invoke` entries on one client, thread-safely (batch
    workers call it concurrently). Entry comes before the `llm_calls` row is
    written, so a call whose row never lands is still counted."""

    def __init__(self, llm: Any) -> None:
        import threading

        self.n = 0
        self._lock = threading.Lock()
        original = llm.invoke

        def invoke(*args: Any, **kwargs: Any) -> Any:
            with self._lock:
                self.n += 1
            return original(*args, **kwargs)

        llm.invoke = invoke


def _call_ids(db: Any) -> set:
    from sqlalchemy import select

    from app.models.llm_call import LLMCall

    return set(db.execute(select(LLMCall.id)).scalars())


def _tokens_since(db: Any, before: set) -> tuple[int | None, int | None, bool]:
    """Input and output tokens over the `llm_calls` rows written since `before`
    -- one per batch, each in its own session -- and whether EVERY such row
    reported an output count. A row with none (a call that failed after the
    provider may have billed it) is not summed, and makes the third value False
    rather than vanishing from the total."""
    from sqlalchemy import select

    from app.models.llm_call import LLMCall

    db.expire_all()
    rows = [r for r in db.execute(select(LLMCall)).scalars() if r.id not in before]

    def total(attr: str) -> int | None:
        values = [getattr(r, attr) for r in rows if getattr(r, attr) is not None]
        return sum(values) if values else None

    complete = bool(rows) and all(r.output_tokens is not None for r in rows)
    return total("input_tokens"), total("output_tokens"), complete


def _calls_since(db: Any, before: set) -> int:
    """How many `llm_calls` rows were written since `before`."""
    from sqlalchemy import select

    from app.models.llm_call import LLMCall

    db.expire_all()
    return sum(1 for i in db.execute(select(LLMCall.id)).scalars() if i not in before)


def _charged_likely(db: Any, before: set, *, answered: int, typed: bool | None) -> bool | None:
    """Whether a failed run's FAILED calls likely billed, read from the
    `llm_calls` rows the run wrote -- `invoke` writes its row before it calls
    the provider -- never assumed (#806 comments 5965066136, 5965088703).

    `answered` is how many of the run's calls came back with an answer; each
    wrote a row. Rows beyond those are failed calls that got as far as the
    provider. With none, no failed call demonstrably reached it -- the SQLite
    lock that killed 10 of 11 batches while inserting their row -- and the
    answer is None, NOT KNOWN, never False: a row lost to a failed commit may
    still have billed (`app/ai/runs.py::_charged_likely`, the same three
    values). With some, it is the failure's own typed value where it carried
    one (`ai_call_boundary`), else True. A batched run's total failure is a
    `RunFailed` carrying none (#800), and a deadline does not say how many
    batches answered, so both pass `answered=0`."""
    rows = _calls_since(db, before)
    if rows <= answered:
        return None
    return True if typed is None else typed


def _seed_profile_if_empty(db: Any, a: Any, admin: Any, client: Any, tiers: Sequence[str]) -> list:
    """Seed the Working Profile through the route's own handler when the
    assessment has no profile rows -- the demo seed creates answers and no
    profile, and the builder refuses an unseeded one. Returns the tiers seeded,
    or [] when rows already existed (nothing is changed then)."""
    from sqlalchemy import func, select

    from app.models.csf_profile import CsfDimensionScore
    from app.routes.csf import _latest_assessment, seed_profiles
    from app.schemas.csf import ProfileSeedRequest

    existing = db.execute(
        select(func.count())
        .select_from(CsfDimensionScore)
        .where(CsfDimensionScore.assessment_id == a.id)
    ).scalar_one()
    if existing or not tiers:
        return []
    if _latest_assessment(db, a.service_id).id != a.id:
        # The handler seeds the service's LATEST assessment, by its own rule:
        # the highest version. `_pick_assessment` takes the newest editable
        # one. No route produces a state where they differ (an older draft
        # beside a newer approved version), so this should normally never
        # fire: it is a ratchet against the two rules drifting apart.
        raise Refused(
            "profile_seed_target_mismatch",
            "The route would seed a different assessment than the one measured.",
        )
    seeded = seed_profiles(
        a.service_id, ProfileSeedRequest(tiers=list(tiers)), user=admin, client=client, db=db
    )
    _log.info("measure_ai_consistency.profile_seeded", assessment_id=str(a.id), tiers=seeded)
    return list(seeded)


def _csf_answer_rows(db: Any, a: Any) -> dict[str, Any]:
    """The answer rows `routes/csf.py::_csf_ai_request_for` reads its notes
    from, by subcategory code, through the same `catalog_rows` filter."""
    from sqlalchemy import select

    from app.csf.retired import catalog_rows
    from app.models.csf_assessment import CsfAnswer

    rows = db.execute(select(CsfAnswer).where(CsfAnswer.assessment_id == a.id)).scalars().all()
    return {r.subcategory_code: r for r in catalog_rows(rows)}


def measure_csf(
    db: Any,
    llm: Any,
    *,
    runs: int,
    reopen_released: bool = False,
    max_output_tokens: int | None = None,
    seed_profile_tiers: Sequence[str] = (),
    stop_on_failure: bool = False,
    probe_batches: int | None = None,
    notes_corpus: NotesCorpus | None = None,
    max_usd: float | None = None,
    price: Mapping[str, float] | None = None,
    progress: Callable[[Sequence[RunRecord]], None] | None = None,
) -> dict:
    """Run csf_score `runs` times on the latest editable CSF assessment, batched
    exactly as the route batches it, and summarize. With `notes_corpus`, the
    corpus's notes are written over the answer rows the route's builder reads
    (`catalog_rows` of the assessment's answers) before it builds the payload.

    A run in which ANY batch failed is a failed run: its missing rows would
    otherwise read as rows the model chose to leave out. The batches' scores are
    split as the route splits them, by its own `_split_strays` (`csf_run_data`):
    an entry naming a row its batch was not asked for is dropped as the route
    drops it (`not_in_batch`, counted per run), and a row answered ONLY that
    way is compared with no agreement."""
    from datetime import timedelta

    from fastapi import HTTPException

    from app.ai.batching import run_batches
    from app.ai.runs import RUN_DEADLINE, RUN_DEADLINE_EXCEEDED, RunFailed
    from app.models._common import utcnow
    from app.models.csf_assessment import CsfAssessment, CsfAssessmentStatus
    from app.routes.csf import _CSF_MAX_WORKERS, _csf_ai_request_for, _csf_batch_inputs

    _require_sqlite_bind(db, "a csf_score measurement")
    admin = _admin_user(db)
    a, reopened_from = _pick_assessment(
        db,
        CsfAssessment,
        CsfAssessmentStatus,
        label="CSF",
        reopen_released=reopen_released,
    )
    client = _client_of(db, a)
    seeded_tiers = _seed_profile_if_empty(db, a, admin, client, seed_profile_tiers)
    corpus_written = None
    if notes_corpus is not None:
        corpus_written = _write_corpus_notes(
            db, _csf_answer_rows(db, a), notes_corpus, client.legal_name
        )
    try:
        req = _csf_ai_request_for(db, a, client)
    except HTTPException as exc:
        raise _builder_refusal(exc) from exc
    corpus_setup = None
    if notes_corpus is not None and corpus_written is not None:
        corpus_setup = _corpus_setup(
            notes_corpus,
            corpus_written[0],
            req.preview.inputs.get("answers") or {},
            corpus_written[1],
        )
    batches = _csf_batch_inputs(req.preview.inputs)
    all_batches = len(batches)
    if probe_batches is not None:
        # A cost probe: the first N of the route's own batches, unchanged. N
        # must be fewer than all of them, or it is a full run under another name.
        if probe_batches >= all_batches:
            raise Refused(
                "probe_not_smaller",
                f"--probe-batches {probe_batches} is not fewer than the "
                f"{all_batches} batches of a full run.",
            )
        batches = batches[:probe_batches]
    rows_sent = sum(len(b["tiers"]) * len(b["subcategories"]) for b in batches)
    has_evidence = {key: bool(row.has_evidence) for key, row in req.rows.items()}
    _log.info(
        "measure_ai_consistency.start",
        job="csf_score",
        assessment_id=str(a.id),
        rows=len(req.rows),
        batches=len(batches),
        answers_sent=len(req.preview.inputs.get("answers") or {}),
        provider=llm.provider.name,
        model=llm.provider.model,
        runs=runs,
    )

    started_calls = _InvokeCounter(llm)

    def one_run(n: int) -> RunRecord:
        before = _call_ids(db)
        started_before = started_calls.n
        try:
            batched = run_batches(
                db,
                llm,
                req.preview.job_name,
                batches,
                requested_by=admin.id,
                service_id=a.service_id,
                client_id=client.id,
                client_org_name=req.preview.client_org_name,
                name_hints=req.preview.name_hints,
                deadline_at=utcnow() + timedelta(seconds=RUN_DEADLINE.total_seconds()),
                max_workers=_CSF_MAX_WORKERS,
                deadline_message="The measurement run did not finish within the run deadline.",
            )
        except (HTTPException, RunFailed) as exc:
            reason, cause, typed = _failure(exc)
            tokens_in, tokens_out, complete = _tokens_since(db, before)
            calls = _calls_since(db, before)
            charged = _charged_likely(db, before, answered=0, typed=typed)
            if isinstance(exc, RunFailed) and exc.reason == RUN_DEADLINE_EXCEEDED:
                # `run_batches` cancels batches not yet started, but one already
                # inside a provider call keeps running and writes its row LATER
                # -- after this count, possibly into the next run's window. The
                # spend so far is therefore not the run's spend.
                complete = False
            _log.error(
                "measure_ai_consistency.run_failed",
                run=n,
                failure=reason,
                cause=cause,
                charged_likely=charged,
            )
            return RunRecord(
                False,
                None,
                reason,
                tokens_in,
                tokens_out,
                cause,
                charged,
                complete,
                calls=calls,
                started=started_calls.n - started_before,
            )
        tokens_in, tokens_out, complete = _tokens_since(db, before)
        calls = _calls_since(db, before)
        if batched.failed:
            failure = f"batches_failed:{batched.failed}/{batched.total}"
            answered = batched.total - batched.failed
            charged = _charged_likely(db, before, answered=answered, typed=None)
            _log.error(
                "measure_ai_consistency.run_failed",
                run=n,
                failure=failure,
                charged_likely=charged,
            )
            return RunRecord(
                False,
                None,
                failure,
                tokens_in,
                tokens_out,
                None,
                charged,
                complete,
                calls=calls,
                started=started_calls.n - started_before,
            )
        data = csf_run_data(batched.inputs, batched.answers, req.rows)
        _log.info(
            "measure_ai_consistency.run_ok",
            run=n,
            batches=batched.total,
            input_tokens=tokens_in,
            output_tokens=tokens_out,
        )
        return RunRecord(
            True,
            data,
            None,
            tokens_in,
            tokens_out,
            tokens_complete=complete,
            calls=calls,
            started=started_calls.n - started_before,
        )

    records = run_loop(
        runs,
        one_run,
        max_output_tokens=max_output_tokens,
        stop_on_failure=stop_on_failure,
        max_usd=max_usd,
        price=price,
        progress=progress,
    )
    report = summarize(
        "csf_score",
        records,
        max_output_tokens=max_output_tokens,
        min_ok_runs=1 if probe_batches is not None else 2,
        context=CsfScope(row_keys=frozenset(req.rows)),
        max_usd=max_usd,
        price=price,
    )
    data_by_run = dict(_ok_runs(records))
    levels = {n: csf_levels(data, has_evidence=has_evidence) for n, data in data_by_run.items()}
    for pair in report["pairs"]:
        pair["level"] = csf_level_agreement(
            levels[pair["pair"][0]], levels[pair["pair"][1]], has_evidence
        )
    report["assessment_id"] = str(a.id)
    report["rows"] = len(req.rows)
    report["batches_per_run"] = len(batches)
    # The (tier, subcategory) rows each run actually ASKED for: all of `rows` on
    # a full run, only the probed batches' rows on a probe.
    report["rows_sent"] = rows_sent
    report["probe"] = (
        None if probe_batches is None else {"batches": len(batches), "of": all_batches}
    )
    report["answers_sent"] = len(req.preview.inputs.get("answers") or {})
    report["input_setup"] = {"reopened_from": reopened_from, "profile_seeded_tiers": seeded_tiers}
    if corpus_setup is not None:
        report["input_setup"]["notes_corpus"] = corpus_setup
    report["provider"] = {"name": llm.provider.name, "model": llm.provider.model}
    report["downstream"] = [
        {
            "run": n,
            "not_scoreable": lv["not_scoreable"],
            "scored_rows": len(lv["levels"]),
            "evidence_capped": lv["evidence_capped"],
            "not_in_batch": data_by_run[n]["not_in_batch"],
        }
        for n, lv in levels.items()
    ]
    return report


def attack_downstream(data: Mapping[str, Any], scope: AttackScope) -> dict:
    """Each technique's R3 status as this run would leave it, computed by the
    engine (`attack.computed.capabilities` / `status_from`).

    Every tool list is resolved with `resolve_citations` and the run's own
    `CitationResolver` (`scope.resolver`), as the apply path resolves it: an unknown tool is
    dropped, and a resolved inference is recorded as an UNCLEARED citation, so
    it counts as awaiting review rather than in place -- which is what a fresh
    run writes. A list that is not a list resolves to nothing, as there.

    NOT modelled, deliberately: locked and edited rows, citations a consultant
    cleared on an earlier run, and planned retirement. This is what the model
    ASKED for, as `zt_downstream` says of its own figure. Rows are indexed as
    `compare_pair` indexes them, so a technique answered twice is in neither.
    `ai_status_differs` counts techniques whose suggested `status` is not the
    computed one."""
    from types import SimpleNamespace

    from app.attack.citations import resolve_citations
    from app.attack.computed import capabilities, status_from

    _require_context("mitre_map", scope)
    resolver = scope.resolver
    index, _, _ = _index(data.get("techniques") or [], ("technique_code",))
    computed: dict[str, str] = {}
    differs = 0
    no_tools: set[str] = set()
    refused: set[str] = set()
    for row in index.values():
        code = row.get("technique_code")
        if not isinstance(code, str):
            continue
        lists: dict[str, list[str]] = {}
        uncleared: list[dict] = []
        for field in _LIST_FIELDS["mitre_map"]:
            out = resolve_citations(row.get(field), resolver)
            lists[field] = list(out.tools)
            uncleared += [
                {"tool": t, "field": field, "cleared_at": None} for t in out.needs_review_tools
            ]
        status = status_from(
            capabilities(
                SimpleNamespace(technique_code=code, unconfirmed_citations=uncleared, **lists)
            )
        )
        computed[code] = status
        differs += int(row.get("status") != status)
        if not any(lists.values()):
            no_tools.add(code)
        if _attack_row_refused(row, scope):
            refused.add(code)
    return {
        "computed_status": computed,
        "ai_status_differs": differs,
        # #867 narrow review at ba31e13f, B2: a technique with NO resolvable
        # tool computes "gap" in every run that cites nothing, and a suggestion
        # the apply path refuses whole writes nothing at all. Neither is an
        # answer the two runs can agree on (`computed_status_agreement`).
        "no_tools": sorted(no_tools),
        "refused": sorted(refused),
    }


def computed_status_agreement(da: Mapping[str, Any], db: Mapping[str, Any]) -> dict:
    """The R3 status agreement between two runs' `attack_downstream`, under the
    absence rule `compare_pair` applies per field: every technique in both is
    COMPARED, and only one where BOTH runs gave a usable answer is `judged`
    and may add to `equal`. The rest are counted, each in exactly one bucket:

    * `refused` -- the apply path writes nothing from it in EITHER run;
    * `both_no_tools` -- no resolvable tool in either run (the field rule's
      `both_absent`);
    * `one_no_tools` -- no resolvable tool in ONE run (`one_absent`; #867
      review B-2). Its computed gap equals the other run's only by accident --
      a run citing only inferred tools computes gap too -- so it is never
      agreement.

    So a prompt that cites fewer tools, in one run or both, cannot score
    higher."""
    sa, sb = da["computed_status"], db["computed_status"]
    both = set(sa) & set(sb)
    no_a, no_b = set(da["no_tools"]), set(db["no_tools"])
    ref = both & (set(da["refused"]) | set(db["refused"]))
    both_no_tools = (both & no_a & no_b) - ref
    one_no_tools = (both & (no_a ^ no_b)) - ref
    judged = both - ref - both_no_tools - one_no_tools
    return {
        "compared": len(both),
        "judged": len(judged),
        "equal": sum(sa[k] == sb[k] for k in judged),
        "both_no_tools": len(both_no_tools),
        "one_no_tools": len(one_no_tools),
        "refused": len(ref),
    }


def _count_values(mapping: Mapping[str, str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in mapping.values():
        out[v] = out.get(v, 0) + 1
    return dict(sorted(out.items()))


def measure_attack(
    db: Any,
    llm: Any,
    *,
    runs: int,
    reopen_released: bool = False,
    max_output_tokens: int | None = None,
    stop_on_failure: bool = False,
    probe_batches: int | None = None,
    max_usd: float | None = None,
    price: Mapping[str, float] | None = None,
    progress: Callable[[Sequence[RunRecord]], None] | None = None,
) -> dict:
    """Run mitre_map `runs` times on the latest editable ATT&CK assessment,
    through the route's own batching (`_run_mitre_map_batched`), and summarize.

    As for csf_score, a run in which ANY batch failed is a failed run, and the
    batches' techniques are concatenated, so a technique answered by two
    batches is a duplicated key, compared in neither run."""
    from dataclasses import replace
    from datetime import timedelta

    from fastapi import HTTPException

    from app.ai.runs import RUN_DEADLINE, RUN_DEADLINE_EXCEEDED, RunFailed
    from app.attack.citations import CitationResolver
    from app.config import get_settings
    from app.models._common import utcnow
    from app.models.attack_assessment import AttackAssessment, AttackAssessmentStatus
    from app.routes.attack import (
        _MITRE_BATCH_SIZE,
        _attack_ai_request_for,
        _refuse_without_capabilities,
        _run_mitre_map_batched,
    )

    _require_sqlite_bind(db, "a mitre_map measurement")
    admin = _admin_user(db)
    a, reopened_from = _pick_assessment(
        db,
        AttackAssessment,
        AttackAssessmentStatus,
        label="ATT&CK",
        reopen_released=reopen_released,
    )
    client = _client_of(db, a)
    try:
        req = _attack_ai_request_for(db, a, client)
        # The run refuses an empty allow-list before calling anything; so does this.
        _refuse_without_capabilities(req, svc_id=a.service_id, client_id=client.id)
    except HTTPException as exc:
        raise _builder_refusal(exc) from exc
    codes = list(req.preview.inputs.get("technique_codes") or [])
    all_batches = -(-len(codes) // _MITRE_BATCH_SIZE)
    if probe_batches is not None:
        if probe_batches >= all_batches:
            raise Refused(
                "probe_not_smaller",
                f"--probe-batches {probe_batches} is not fewer than the "
                f"{all_batches} batches of a full run.",
            )
        # The first N of the route's own batches: the route splits
        # `technique_codes` in order, so its first N * size codes are exactly them.
        probed = codes[: probe_batches * _MITRE_BATCH_SIZE]
        req = replace(
            req,
            preview=replace(req.preview, inputs={**req.preview.inputs, "technique_codes": probed}),
        )
    sent = len(req.preview.inputs["technique_codes"])
    batches = -(-sent // _MITRE_BATCH_SIZE)
    # Built as `_attack_run_work` builds it, from the same request.
    resolver = CitationResolver(
        req.capabilities,
        client_org_name=req.preview.client_org_name,
        redaction_mode=get_settings().shield_redaction_mode,
        name_hints=tuple(req.preview.name_hints or ()),
    )
    # What the apply path checks each suggestion against: the assessment's
    # rows (`req.rows`, the dict `_attack_run_work` indexes) and the resolver.
    scope = AttackScope(resolver=resolver, assessment_codes=frozenset(req.rows))
    _log.info(
        "measure_ai_consistency.start",
        job="mitre_map",
        assessment_id=str(a.id),
        techniques=sent,
        batches=batches,
        tools=len(req.capabilities),
        provider=llm.provider.name,
        model=llm.provider.model,
        runs=runs,
    )

    started_calls = _InvokeCounter(llm)

    def one_run(n: int) -> RunRecord:
        before = _call_ids(db)
        started_before = started_calls.n
        try:
            suggestions, total, failed = _run_mitre_map_batched(
                db,
                llm,
                req,
                requested_by=admin.id,
                service_id=a.service_id,
                client_id=client.id,
                deadline_at=utcnow() + timedelta(seconds=RUN_DEADLINE.total_seconds()),
            )
        except (HTTPException, RunFailed) as exc:
            reason, cause, typed = _failure(exc)
            tokens_in, tokens_out, complete = _tokens_since(db, before)
            calls = _calls_since(db, before)
            charged = _charged_likely(db, before, answered=0, typed=typed)
            if isinstance(exc, RunFailed) and exc.reason == RUN_DEADLINE_EXCEEDED:
                # As for csf_score: a batch still inside a provider call writes
                # its row later, so the spend so far is not the run's spend.
                complete = False
            _log.error(
                "measure_ai_consistency.run_failed",
                run=n,
                failure=reason,
                cause=cause,
                charged_likely=charged,
            )
            return RunRecord(
                False,
                None,
                reason,
                tokens_in,
                tokens_out,
                cause,
                charged,
                complete,
                calls=calls,
                started=started_calls.n - started_before,
            )
        tokens_in, tokens_out, complete = _tokens_since(db, before)
        calls = _calls_since(db, before)
        if failed:
            failure = f"batches_failed:{failed}/{total}"
            charged = _charged_likely(db, before, answered=total - failed, typed=None)
            _log.error(
                "measure_ai_consistency.run_failed",
                run=n,
                failure=failure,
                charged_likely=charged,
            )
            return RunRecord(
                False,
                None,
                failure,
                tokens_in,
                tokens_out,
                None,
                charged,
                complete,
                calls=calls,
                started=started_calls.n - started_before,
            )
        _log.info(
            "measure_ai_consistency.run_ok",
            run=n,
            batches=total,
            input_tokens=tokens_in,
            output_tokens=tokens_out,
        )
        data = {"techniques": suggestions}
        return RunRecord(
            True,
            data,
            None,
            tokens_in,
            tokens_out,
            tokens_complete=complete,
            calls=calls,
            started=started_calls.n - started_before,
        )

    records = run_loop(
        runs,
        one_run,
        max_output_tokens=max_output_tokens,
        stop_on_failure=stop_on_failure,
        max_usd=max_usd,
        price=price,
        progress=progress,
    )
    report = summarize(
        "mitre_map",
        records,
        max_output_tokens=max_output_tokens,
        # A single-run probe sizes cost; two or more runs of the same probed
        # batches are compared like any measurement (#736 comment 6068587667).
        min_ok_runs=1 if runs == 1 else 2,
        context=scope,
        max_usd=max_usd,
        price=price,
    )
    computed = {n: attack_downstream(data, scope) for n, data in _ok_runs(records)}
    for pair in report["pairs"]:
        pair["computed_status"] = computed_status_agreement(
            computed[pair["pair"][0]], computed[pair["pair"][1]]
        )
    report["assessment_id"] = str(a.id)
    report["techniques_sent"] = sent
    report["batches_per_run"] = batches
    report["tools_available"] = len(req.capabilities)
    report["probe"] = None if probe_batches is None else {"batches": batches, "of": all_batches}
    report["input_setup"] = {"reopened_from": reopened_from}
    report["provider"] = {"name": llm.provider.name, "model": llm.provider.model}
    report["downstream"] = [
        {
            "run": n,
            "computed_status_counts": _count_values(c["computed_status"]),
            "ai_status_differs": c["ai_status_differs"],
        }
        for n, c in computed.items()
    ]
    return report


#: `--inventory` file suffix -> the MIME type the upload route would record for
#: it. Only formats `tech_debt/parsers.py::SUPPORTED_MIME` reads.
_INVENTORY_MIME = {
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _inventory_rows(path: str) -> tuple[list[dict], str]:
    """The rows of `path`, parsed by the upload's own `parse_inventory`."""
    from pathlib import Path

    from app.tech_debt.parsers import UnsupportedInventoryFormat, parse_inventory

    suffix = Path(path).suffix.lower()
    mime = _INVENTORY_MIME.get(suffix)
    if mime is None:
        raise Refused(
            "inventory_format", f"--inventory must be .csv or .xlsx, not {suffix or 'no suffix'!r}."
        )
    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        raise Refused("inventory_unreadable", f"--inventory could not be read: {exc}") from exc
    try:
        rows = parse_inventory(data, mime)
    except UnsupportedInventoryFormat as exc:
        raise Refused("inventory_format", str(exc)) from exc
    if not rows:
        raise Refused("inventory_empty", "--inventory holds no rows.")
    return rows, mime


def _item_record(item: Any) -> dict:
    """An `ExtractedCapability` as the dict `compare_pair` reads."""
    from dataclasses import asdict

    record = asdict(item)
    record["security_functions"] = list(record["security_functions"])
    return record


_TRI_STATE = {True: "true", False: "false", None: "null"}


def measure_tech_debt(
    db: Any,
    llm: Any,
    *,
    runs: int,
    inventory: str,
    service_id: str,
    max_output_tokens: int | None = None,
    stop_on_failure: bool = False,
    max_usd: float | None = None,
    price: Mapping[str, float] | None = None,
    progress: Callable[[Sequence[RunRecord]], None] | None = None,
) -> dict:
    """Run tech_debt_extract `runs` times on the rows of `inventory`, through
    `extract_from_rows` (the extraction's own call), for the Tech Debt service
    named by `service_id`, and summarize. `extract_from_rows` writes only its
    `llm_calls` row; the capability list and items are the ROUTE's to write.

    WHY THE SERVICE IS NAMED, NEVER PICKED: the inventory file carries no link
    to any client, and redaction is per tenant -- the service's client's legal
    name and its users' names are what the redactor replaces. Picking "the
    newest Tech Debt service" would redact one client's export with ANOTHER
    client's names, leaving its own unredacted while every refusal passed. The
    operator must say whose inventory this is; the report records the client
    whose names were used."""
    import uuid as _uuid
    from pathlib import Path

    from fastapi import HTTPException

    from app.models.service import Service, ServiceKind
    from app.tech_debt.extract import (
        client_org_name_for_tenant,
        extract_from_rows,
        name_hints_for_tenant,
    )

    _require_sqlite_bind(db, "a tech_debt_extract measurement")
    admin = _admin_user(db)
    rows, mime = _inventory_rows(inventory)
    try:
        svc = db.get(Service, _uuid.UUID(str(service_id)))
    except ValueError as exc:
        raise Refused("service_id_invalid", f"--service-id {service_id!r} is not a UUID.") from exc
    if svc is None or svc.kind != ServiceKind.TECH_DEBT:
        raise Refused(
            "no_tech_debt_service",
            f"--service-id {service_id} names no Tech Debt service in this database.",
        )
    org_name = client_org_name_for_tenant(db, svc.client_id)
    hints = name_hints_for_tenant(db, svc.client_id)
    # The synthetic corpus names its client by placeholder (#806 section 2's
    # "[CLIENT] name" row): filled with the NAMED client's legal name, so the
    # redactor below replaces a real name -- refused when there is none.
    _require_client_name(
        [v for r in rows for v in r.values() if isinstance(v, str)], org_name, "--inventory"
    )
    filled = 0
    for r in rows:
        for k, v in r.items():
            if isinstance(v, str):
                r[k], n = _fill_client_name(v, org_name)
                filled += n
    _log.info(
        "measure_ai_consistency.start",
        job="tech_debt_extract",
        service_id=str(svc.id),
        rows=len(rows),
        provider=llm.provider.name,
        model=llm.provider.model,
        runs=runs,
    )
    reconciliations: dict[int, dict] = {}

    started_calls = _InvokeCounter(llm)

    def one_run(n: int) -> RunRecord:
        before = _call_ids(db)
        started_before = started_calls.n
        try:
            result = extract_from_rows(
                db=db,
                rows=rows,
                source_filename=Path(inventory).name,
                source_mime=mime,
                requested_by_id=admin.id,
                service_id=svc.id,
                client_id=svc.client_id,
                client_org_name=org_name,
                name_hints=hints,
                llm=llm,
            )
        except (HTTPException, ValueError) as exc:
            # ValueError is the parser refusing the response, which the route
            # reports as `ai_extraction_unparseable`. Committed first, as the
            # route commits, so the call's `llm_calls` row is counted.
            db.commit()
            reason, cause, typed = _failure(exc)
            tokens_in, tokens_out, complete = _tokens_since(db, before)
            calls = _calls_since(db, before)
            charged = _charged_likely(db, before, answered=0, typed=typed)
            _log.error(
                "measure_ai_consistency.run_failed",
                run=n,
                failure=reason,
                cause=cause,
                charged_likely=charged,
            )
            return RunRecord(
                False,
                None,
                reason,
                tokens_in,
                tokens_out,
                cause,
                charged,
                complete,
                calls=calls,
                started=started_calls.n - started_before,
            )
        db.commit()
        tokens_in, tokens_out, complete = _tokens_since(db, before)
        calls = _calls_since(db, before)
        rec = result.reconciliation
        reconciliations[n] = {
            "excluded_row_indexes": sorted(e.index for e in rec.excluded_rows),
            "attribution_complete": rec.attribution_complete,
            "security_related": _count_values(
                {str(i): _TRI_STATE[item.security_related] for i, item in enumerate(result.items)}
            ),
        }
        _log.info(
            "measure_ai_consistency.run_ok",
            run=n,
            items=len(result.items),
            input_tokens=tokens_in,
            output_tokens=tokens_out,
        )
        data = {"items": [_item_record(i) for i in result.items]}
        return RunRecord(
            True,
            data,
            None,
            tokens_in,
            tokens_out,
            tokens_complete=complete,
            calls=calls,
            started=started_calls.n - started_before,
        )

    records = run_loop(
        runs,
        one_run,
        max_output_tokens=max_output_tokens,
        stop_on_failure=stop_on_failure,
        max_usd=max_usd,
        price=price,
        progress=progress,
    )
    report = summarize(
        "tech_debt_extract",
        records,
        max_output_tokens=max_output_tokens,
        max_usd=max_usd,
        price=price,
    )
    report["service_id"] = str(svc.id)
    # Whose names the redactor used: the client the operator named, by id.
    report["redaction_client_id"] = str(svc.client_id)
    report["rows_sent"] = len(rows)
    report["input_setup"] = {
        "inventory": Path(inventory).name,
        "mime": mime,
        "client_name_substituted": filled,
    }
    report["provider"] = {"name": llm.provider.name, "model": llm.provider.model}
    report["downstream"] = [{"run": n, **r} for n, r in reconciliations.items()]
    return report


def _print_table(report: dict) -> None:
    print(f"job={report['job']} runs_ok={report['runs_ok']}/{report['runs_requested']}")
    for f in report["failed_runs"]:
        print(f"  run {f['run']} FAILED: {f['failure']} (charged_likely: {f['charged_likely']})")
    for p in report["pairs"]:
        r = p["rows"]
        print(
            f"pair {p['pair']}: rows in both {r['in_both']}, only A {r['only_in_a']}, "
            f"only B {r['only_in_b']}, "
            + (
                f"unreadable n/a (dropped upstream), unkeyable {r['unkeyable_a']}/"
                f"{r['unkeyable_b']}, "
                if r["unreadable_a"] is None
                else f"unreadable {r['unreadable_a']}/{r['unreadable_b']}, "
            )
            + f"duplicate keys {r['duplicate_keys_a']}/{r['duplicate_keys_b']}"
        )
        for name, s in p["fields"].items():
            if "mean_jaccard" in s:
                print(
                    f"  {name}: same set {s['equal']}/{s['compared']}, mean Jaccard "
                    f"{s['mean_jaccard']} over all {s['compared']} compared (absent in "
                    f"both {s['both_absent']}, in one {s['one_absent']}, not a list "
                    f"{s['not_a_list']}: NO agreement; {s['judged']} judged), missing A/B "
                    f"{s['missing_in_a']}/{s['missing_in_b']}"
                )
                continue
            print(
                f"  {name}: equal {s['equal']}/{s['compared']}, within one "
                f"{s['within_one']}/{s['compared']}, absent in both {s['both_absent']}, "
                f"in one {s['one_absent']} (no agreement), mean |diff| {s['mean_abs_diff']}, "
                f"missing A/B {s['missing_in_a']}/{s['missing_in_b']}"
            )
        if "computed_status" in p:
            cs = p["computed_status"]
            print(
                f"  computed R3 status: equal {cs['equal']}/{cs['compared']} (no tool in "
                f"both runs {cs['both_no_tools']}, refused in either {cs['refused']}: "
                "no agreement)"
            )
    for e in report.get("echo", []):
        for name, c in e.items():
            if name != "run":
                print(
                    f"run {e['run']} echo {name}: {c['echoed']}/{c['sent_and_answered']} "
                    f"repeat the sent value ({c['nothing_sent']} rows were sent nothing)"
                )
    for p in report["pairs"]:
        if "level" in p:
            lv = p["level"]
            print(
                f"pair {p['pair']} maturity level: equal {lv['equal']}/{lv['compared']} "
                f"({lv['no_evidence_rows']} of those rows have no evidence: capped at Level 2)"
            )
    for d in report.get("downstream", []):
        if "total_gap_count" in d:
            print(
                f"run {d['run']}: client-visible gaps {d['total_gap_count']}, "
                f"unscored {d['unscored_count']}, non-integer values {d['non_integer_values']}, "
                f"out-of-range values {d['out_of_range_values']}, "
                f"unusable targets {len(d['unusable_target_codes'])}"
            )
        elif "computed_status_counts" in d:
            print(
                f"run {d['run']}: computed R3 statuses {d['computed_status_counts']}, "
                f"AI status differs from computed on {d['ai_status_differs']}"
            )
        elif "excluded_row_indexes" in d:
            print(
                f"run {d['run']}: excluded rows {d['excluded_row_indexes']}, "
                f"attribution complete {d['attribution_complete']}, "
                f"security_related {d['security_related']}"
            )
        else:
            print(
                f"run {d['run']}: rows scored {d['scored_rows']}, "
                f"not scoreable {d['not_scoreable']}, evidence-capped {d['evidence_capped']}"
            )
    asked = report.get(
        "rows_sent", report.get("techniques_sent", report.get("assessment_capabilities"))
    )
    print(f"rows asked per run: {asked}")
    if report.get("probe"):
        print(f"PROBE: {report['probe']['batches']} of {report['probe']['of']} batches")
    corpus = report.get("input_setup", {}).get("notes_corpus")
    if corpus:
        sent = ", ".join(f"{name} {c['sent']}/{c['rows']}" for name, c in corpus["classes"].items())
        print(f"notes corpus {corpus['corpus']}: rows sent per class {sent}")
    t, b = report["tokens"], report["budget"]
    print(
        f"tokens: input {t['input']}, output {t['output']}, "
        f"complete {t['complete']}"
        + ("" if t["complete"] else " (a call reported no tokens: spend is UNDERSTATED)")
    )
    if b["max_output_tokens"] is not None:
        print(
            f"budget: {b['spent_output_tokens']} of {b['max_output_tokens']} output tokens"
            + (" -- OVERRUN" if b["overrun"] else "")
            + ("" if b["complete"] else " (count INCOMPLETE)")
        )


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--job", required=True)
    p.add_argument("--framework", choices=("cisa", "dod"), default="cisa")
    p.add_argument("--runs", type=int, default=2)
    p.add_argument("--out", required=True)
    p.add_argument(
        "--reopen-released",
        action="store_true",
        help="If no assessment is editable, set the latest released one back to DRAFT "
        "first (the demo seed releases them all). Recorded in the report.",
    )
    p.add_argument(
        "--seed-profile-tiers",
        default="",
        help="csf_score only: comma-separated tiers (high,moderate,low) to seed, through "
        "the route's own handler, when the assessment has no Working Profile rows. "
        "Recorded in the report.",
    )
    p.add_argument(
        "--probe-batches",
        type=int,
        default=None,
        help="csf_score and mitre_map only: run just the first N of the route's batches. "
        "With --runs 1 it sizes per-batch cost and reports no agreement. mitre_map also "
        "allows --runs 2 or more over the same batches, compared like a full measurement.",
    )
    p.add_argument(
        "--inventory",
        default=None,
        help="tech_debt_extract only, and required for it: the .csv or .xlsx whose rows "
        "are extracted, parsed by the upload's own parser.",
    )
    p.add_argument(
        "--service-id",
        default=None,
        help="tech_debt_extract only, and required for it: the Tech Debt service whose "
        "client the inventory belongs to. Its client's names are what the redactor "
        "replaces, so it is never guessed.",
    )
    p.add_argument(
        "--notes-corpus",
        default=None,
        help="zt_score and csf_score only: a notes corpus (scripts/measure_corpus/notes.json) "
        "whose notes are written over the measured assessment's answer rows before the "
        "route's builder runs. Recorded in the report.",
    )
    p.add_argument(
        "--stop-on-failure",
        action="store_true",
        help="Start no further run after a failed one (a rate limit is not retried into).",
    )
    p.add_argument(
        "--max-output-tokens",
        type=int,
        default=None,
        help="Optional, OUTPUT tokens only: start no further run once this many are "
        "spent. The dollar guard from the #806 cost caps (input and output) always "
        "applies besides.",
    )
    args = p.parse_args(argv)
    if args.probe_batches is not None and (args.job not in _BATCHED_JOBS or args.probe_batches < 1):
        print(
            "REFUSED (probe_not_applicable): --probe-batches is for "
            f"{' and '.join(_BATCHED_JOBS)} only, >= 1.",
            file=sys.stderr,
        )
        return 2
    if (args.inventory is None) == (args.job == "tech_debt_extract"):
        # Either way round is a mistake: tech_debt_extract has no other input,
        # and an inventory given to another job would be silently ignored.
        print(
            "REFUSED (inventory_mismatch): --inventory is required for "
            "tech_debt_extract and accepted for no other job.",
            file=sys.stderr,
        )
        return 2
    if (args.service_id is None) == (args.job == "tech_debt_extract"):
        # The inventory names no client, and redaction is per client: the
        # operator says whose it is, or the run does not start.
        print(
            "REFUSED (service_id_mismatch): --service-id is required for "
            "tech_debt_extract (it decides whose names are redacted) and accepted "
            "for no other job.",
            file=sys.stderr,
        )
        return 2
    if args.reopen_released and args.job == "tech_debt_extract":
        print(
            "REFUSED (reopen_not_applicable): tech_debt_extract measures an inventory "
            "file, not an assessment, so there is nothing to reopen.",
            file=sys.stderr,
        )
        return 2
    compared_probe = args.job in _COMPARED_PROBE_JOBS and args.runs >= 2
    if args.probe_batches is not None and args.runs != 1 and not compared_probe:
        print(
            "REFUSED (probe_runs_not_one): a probe is a single run, except that "
            f"{' and '.join(_COMPARED_PROBE_JOBS)} may compare two or more runs of the "
            "same probed batches.",
            file=sys.stderr,
        )
        return 2
    if args.runs < 2 and args.probe_batches is None:
        print("REFUSED (runs_below_two): agreement needs at least two runs.", file=sys.stderr)
        return 2
    if args.runs > MAX_RUNS:
        print(f"REFUSED (runs_above_max): at most {MAX_RUNS} runs.", file=sys.stderr)
        return 2
    if args.notes_corpus is not None and args.job not in _NOTES_JOBS:
        print(
            "REFUSED (notes_corpus_not_applicable): --notes-corpus is for "
            f"{' and '.join(_NOTES_JOBS)} only; {args.job} sends no interview notes.",
            file=sys.stderr,
        )
        return 2

    from app.config import get_settings

    s = get_settings()
    try:
        preflight(
            database_url=s.database_url,
            llm_mode=s.shield_llm_mode,
            redaction_mode=s.shield_redaction_mode,
        )
        if args.job not in _IMPLEMENTED_JOBS:
            _job_shape(args.job)
        price = price_for(s.shield_llm_provider, s.shield_llm_model)
        corpus = None if args.notes_corpus is None else load_notes_corpus(args.notes_corpus)
        # Reserve the name now (exclusive create), before any provider exists.
        # Every later write replaces it atomically (`_ReportFile.write`).
        _open_report(args.out).close()
    except Refused as exc:
        print(f"REFUSED ({exc.reason}): {exc}", file=sys.stderr)
        return 2
    max_usd = side_cap_usd(args.job)
    database_url = database_url_params(s.database_url)
    price_basis = {
        "provider": s.shield_llm_provider,
        "model": s.shield_llm_model,
        "usd_per_mtok": price,
    }
    report_file = _ReportFile(Path(args.out), args.job, max_usd, price, database_url)
    print(
        f"budget: ${max_usd} for this side (half the ${COST_CAPS_USD[args.job]} service cap), "
        f"input and output at the {s.shield_llm_provider}/{s.shield_llm_model} list price. "
        "A later run is not STARTED if the spend so far plus the largest run so far would "
        "cross it. The FIRST run is not bounded in advance."
    )
    if database_url["sqlite_timeout"] is None:
        print(
            "DATABASE_URL sets no ?timeout=: a batched job's workers can hit SQLite's "
            "default busy timeout (#806 comment 5965066136)."
        )
    try:
        for sentinel in _PARSER_SENTINELS.get(args.job, {}).values():
            # Read BEFORE any provider exists (#867 review A1): a parser that
            # can no longer produce its sentinel fails here, not after the
            # paid runs.
            sentinel()
        report = _measure(args, corpus, max_usd, price, report_file)
        report["cost_cap"] = {
            "service_cap_usd": COST_CAPS_USD[args.job],
            "side_cap_usd": max_usd,
            "price_basis": price_basis,
            # Complete only when every started call is accounted for by a
            # row with tokens (`tokens.complete`).
            "estimated_usd": round(
                _usd(report["tokens"]["input"], report["tokens"]["output"], price), 4
            ),
            "estimate_complete": report["tokens"]["complete"],
        }
        report["database_url"] = database_url
        report["provider_calls_started"] = report_file.provider_calls_started
        report["status"] = "complete"
        # Inside the handler (#952 narrow review 2): a failure here leaves the
        # last in-progress report on disk, never a half-written one.
        report_file.write(report)
    except BaseException as exc:
        if report_file.provider_calls_started == 0:
            # No provider call was even started: nothing was spent, and there
            # is no run to keep. The file this run reserved empty goes.
            Path(args.out).unlink()
        else:
            # #952 review F2: something may have been billed. Keep every
            # completed run, and say why the report stops where it does.
            report_file.abort(exc)
        if isinstance(exc, Refused):
            print(f"REFUSED ({exc.reason}): {exc}", file=sys.stderr)
            return 2
        raise
    _print_table(report)
    cap = report["cost_cap"]
    print(
        f"estimated spend ${cap['estimated_usd']} at list price, against ${max_usd} for "
        f"this side of a ${cap['service_cap_usd']} service cap"
        + ("" if cap["estimate_complete"] else " (count INCOMPLETE: spend is UNDERSTATED)")
    )
    return report["exit_code"]


def database_url_params(url: str) -> dict:
    """The DATABASE_URL's query parameters, and the SQLite busy timeout among
    them: never the scheme, host, path or credentials. The live run sets
    `?timeout=900` by hand (#736 comment 6068587667), so the report records
    exactly what it ran with, and `None` when there was no timeout."""
    from urllib.parse import parse_qsl, urlsplit

    query = dict(parse_qsl(urlsplit(url).query, keep_blank_values=True))
    return {"query": query, "sqlite_timeout": query.get("timeout")}


def _dump_json(obj: Any, fh: Any) -> None:
    json.dump(obj, fh, indent=2, sort_keys=True)


class _ReportFile:
    """`--out`, replaced ATOMICALLY after every run (#952 review F2 and narrow
    review 2): each write goes to a temporary file in the same directory, is
    fsynced, then `os.replace`d over `--out`. So at any moment the file is
    either the last complete write -- every run completed up to it -- or the
    empty file reserved at start; never half a JSON document. It also counts
    the provider calls STARTED, where `LLMClient.invoke` is entered."""

    def __init__(
        self,
        path: Path,
        job: str,
        max_usd: float,
        price: Mapping[str, float],
        database_url: dict,
    ) -> None:
        self.path = path
        self.job = job
        self.max_usd = max_usd
        self.price = price
        self.database_url = database_url
        self.counter: Any = None
        self.records: list[RunRecord] = []

    @property
    def provider_calls_started(self) -> int:
        return 0 if self.counter is None else self.counter.n

    def count_calls(self, llm: Any) -> None:
        self.counter = _InvokeCounter(llm)

    def write(self, report: dict) -> None:
        import os
        import tempfile

        fd, tmp = tempfile.mkstemp(
            dir=self.path.parent, prefix=f".{self.path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                _dump_json(report, fh)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def partial(self, status: str) -> dict:
        rows = [run_row(i + 1, r, self.price) for i, r in enumerate(self.records)]
        known = [r["estimated_usd"] for r in rows if r["estimated_usd"] is not None]
        return {
            "job": self.job,
            "status": status,
            "runs": rows,
            "spent_usd": round(sum(known), 6),
            "spent_usd_complete": len(known) == len(rows),
            "max_usd": self.max_usd,
            "database_url": self.database_url,
            "provider_calls_started": self.provider_calls_started,
        }

    def progress(self, records: Sequence[RunRecord]) -> None:
        self.records = list(records)
        self.write(self.partial("in_progress"))

    def abort(self, exc: BaseException) -> None:
        report = self.partial("aborted")
        # The exception's TYPE only: a message can quote the model.
        report["aborted"] = {
            "exception": type(exc).__name__,
            "after_runs": len(self.records),
            "note": "a run under way when this happened is not in `runs`; "
            "`provider_calls_started` counts its calls",
        }
        try:
            self.write(report)
        except Exception as write_exc:  # noqa: BLE001 - logged; the cause wins
            # The last in-progress report is still on disk, whole. The ORIGINAL
            # exception is the one `main` re-raises.
            _log.error(
                "measure_ai_consistency.abort_write_failed",
                error=type(write_exc).__name__,
                cause=type(exc).__name__,
            )
            return
        _log.error(
            "measure_ai_consistency.aborted",
            exception=type(exc).__name__,
            runs_kept=len(self.records),
            provider_calls_started=self.provider_calls_started,
        )


def _open_report(path: str) -> Any:
    """Create `--out` now, before any provider exists (#806 comment 5965052688:
    a bad path found after the paid runs loses the report). Exclusive: an
    existing file is an earlier run's report, possibly the only record of a
    paid run, and is never overwritten."""
    try:
        return open(path, "x", encoding="utf-8")  # noqa: SIM115 - closed by main
    except FileExistsError as exc:
        raise Refused("out_exists", f"--out {path} already exists; name a new file.") from exc
    except OSError as exc:
        raise Refused("out_unwritable", f"--out {path} cannot be created: {exc}") from exc


def _measure(
    args: argparse.Namespace,
    corpus: Any,
    max_usd: float,
    price: Mapping[str, float],
    report_file: Any,
) -> dict:
    """Build the provider and run the measurement `args` names. A refusal is
    raised as `Refused` for `main` to report."""
    from app.ai.llm import LLMClient
    from app.config import get_settings
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        llm = LLMClient.from_db(db, get_settings())
        report_file.count_calls(llm)
        print(f"provider={llm.provider.name} model={llm.provider.model} runs={args.runs}")
        common = {
            "runs": args.runs,
            "reopen_released": args.reopen_released,
            "max_output_tokens": args.max_output_tokens,
            "stop_on_failure": args.stop_on_failure,
            "max_usd": max_usd,
            "price": price,
            "progress": report_file.progress,
        }
        if args.job == "csf_score":
            tiers = [t for t in args.seed_profile_tiers.split(",") if t]
            return measure_csf(
                db,
                llm,
                seed_profile_tiers=tiers,
                probe_batches=args.probe_batches,
                notes_corpus=corpus,
                **common,
            )
        if args.job == "mitre_map":
            return measure_attack(db, llm, probe_batches=args.probe_batches, **common)
        if args.job == "tech_debt_extract":
            # No assessment to reopen (refused above): the input is the file.
            common.pop("reopen_released")
            return measure_tech_debt(
                db, llm, inventory=args.inventory, service_id=args.service_id, **common
            )
        return measure_zt(db, llm, framework=args.framework, notes_corpus=corpus, **common)


if __name__ == "__main__":
    raise SystemExit(main())
