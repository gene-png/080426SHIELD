"""One-command live-AI smoke (Sprint 6 T1 / D-026).

Reproduces the 2026-07-12 manual smoke that first proved the Anthropic live
path: build a CSF-narrative (`csf_score`) payload carrying DELIBERATE PII, send
it through the single redacting egress seam (`LLMClient.invoke`, via the AI
engine's `run_job`), then print the real model response together with the
`llm_calls` audit row. Lets any developer validate a provider key in one
command and see the redaction/audit contract hold against a real call.

Usage (inside the api container, with a real key exported):
  docker compose exec -T \\
    -e SHIELD_LLM_MODE=live -e ANTHROPIC_API_KEY=sk-ant-... \\
    api python -m scripts.smoke_live_ai

Refuses to run in fixture mode or with an unrunnable live config — it FAILS
LOUDLY (non-zero exit) rather than pretend a keyless run exercised anything.
The canonical PII payload lives here in `build_csf_pii_inputs()`; the opt-in
live test (`tests/live/test_live_ai.py`) imports the SAME builder so the
automated check and the manual smoke can never drift apart.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

# Make `import app.*` / `import scripts.*` work when invoked from anywhere.
APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

# The deliberate-PII fixture. Each PII item appears TWICE so redaction has real
# work to do and the observed counts are unambiguous: the 2026-07-12 smoke
# stripped {client_org: 2, name: 2, email: 2} in strict mode.
CLIENT_ORG = "Atlas Corporation"
CONTACT_NAME = "Jane Doe"
CONTACT_EMAIL = "jane.doe@atlascorp.example"

# What redaction MUST strip from the payload above under strict mode. The keys
# are redact.py's category names; the values are occurrence counts.
EXPECTED_REDACTED_COUNTS = {"email": 2, "name": 2, "client_org": 2}

# Raw PII strings that must NOT appear anywhere in the real model response.
PII_STRINGS = (CLIENT_ORG, CONTACT_NAME, CONTACT_EMAIL)


def build_csf_pii_inputs() -> tuple[dict, str, tuple[str, ...]]:
    """Return (inputs, client_org_name, name_hints) for a `csf_score` run whose
    interview notes embed org/name/email PII twice each."""
    notes = (
        f"{CLIENT_ORG} governance is owned by {CONTACT_NAME}. Reach "
        f"{CONTACT_NAME} at {CONTACT_EMAIL} for the {CLIENT_ORG} "
        f"risk-council charter and supporting evidence ({CONTACT_EMAIL})."
    )
    inputs = {
        "tiers": ["high"],
        "subcategories": ["GV.OC-01"],
        "answers": {
            "GV.OC-01": {
                "maturity_tier": "high",
                "has_evidence": True,
                "notes": notes,
            }
        },
    }
    return inputs, CLIENT_ORG, (CONTACT_NAME,)


def _ephemeral_sessionmaker():
    """A throwaway migrated SQLite DB so the smoke needs only a key, not a
    running Postgres. The `llm_calls` row is written here and read back."""
    import tempfile

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    tmpdir = tempfile.mkdtemp(prefix="shield-live-smoke-")
    url = f"sqlite:///{Path(tmpdir) / 'smoke.db'}"
    os.environ["DATABASE_URL"] = url
    cfg = Config(str(APP_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(APP_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _make_admin(db):
    from app.models.user import User, UserRole

    user = User(
        email=f"smoke-{uuid.uuid4().hex[:8]}@kentro.example",
        password_hash="x" * 64,
        role=UserRole.ADMIN,
        display_name="Live Smoke",
    )
    db.add(user)
    db.flush()
    return user


def run_smoke() -> int:
    """Run the live smoke. Returns a process exit code (0 = pass)."""
    from app.ai.engine import run_job
    from app.ai.llm import LLMClient
    from app.config import get_settings
    from app.models.llm_call import LLMCallMode, LLMCallStatus

    settings = get_settings()

    if settings.shield_llm_mode != "live":
        print(
            "REFUSING: SHIELD_LLM_MODE is not 'live' — set SHIELD_LLM_MODE=live "
            "and a provider key. This smoke exercises the REAL egress path only.",
            file=sys.stderr,
        )
        return 2

    ready, detail = settings.live_llm_readiness()
    if not ready:
        print(f"REFUSING: live config is not runnable — {detail}", file=sys.stderr)
        return 2

    print(f"[smoke] {detail}")
    inputs, client_org_name, name_hints = build_csf_pii_inputs()

    session_factory = _ephemeral_sessionmaker()
    client = LLMClient.from_settings(settings)
    with session_factory() as db:
        admin = _make_admin(db)
        result = run_job(
            db,
            client,
            "csf_score",
            inputs=inputs,
            requested_by=admin.id,
            client_org_name=client_org_name,
            name_hints=name_hints,
        )
        db.commit()
        row = result.llm_call

        print("\n=== llm_calls row ===")
        print(f"  provider        = {row.provider}")
        print(f"  model           = {row.model}")
        print(f"  mode            = {row.mode.value}")
        print(f"  status          = {row.status.value}")
        print(f"  input_tokens    = {row.input_tokens}")
        print(f"  output_tokens   = {row.output_tokens}")
        print(f"  duration_ms     = {row.duration_ms}")
        print(f"  redacted_counts = {row.redacted_counts}")
        print(f"  error_message   = {row.error_message}")

        print("\n=== parsed response (draft suggestion) ===")
        print(result.data)

        # Loud assertions: the contract the smoke exists to prove.
        assert row.mode == LLMCallMode.LIVE, "expected a LIVE call, got fixture"
        assert row.status == LLMCallStatus.COMPLETED, f"call did not complete: {row.status}"
        assert row.error_message is None, f"unexpected error: {row.error_message}"
        assert row.input_tokens and row.output_tokens, "token usage not recorded"
        assert (
            row.redacted_counts == EXPECTED_REDACTED_COUNTS
        ), f"redaction counts drifted: {row.redacted_counts} != {EXPECTED_REDACTED_COUNTS}"
        leaked = [s for s in PII_STRINGS if s in str(result.data)]
        assert not leaked, f"PII leaked into the response: {leaked}"

    print("\n[smoke] PASS — real live call, redaction + audit row + no-PII all held.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_smoke())
