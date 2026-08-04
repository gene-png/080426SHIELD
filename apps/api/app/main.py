"""FastAPI application factory.

Master Spec §4 + AI Prompt §4.4: structured logging, correlation IDs, global
exception handler, no stack traces to user, env-configurable everything.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.config import get_settings
from app.exceptions import register_exception_handlers
from app.logging import configure_logging, get_logger
from app.middleware.correlation import CorrelationIdMiddleware
from app.routes import (
    admin,
    ai_preview,
    artifacts,
    attack,
    auth,
    clients,
    csf,
    health,
    intake,
    messages,
    notifications,
    oidc,
    risk,
    tech_debt,
    zt,
)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    settings.assert_safe_for_runtime()

    log = get_logger("app.startup")
    log.info(
        "api_starting",
        version=__version__,
        environment=settings.environment,
        llm_provider=settings.shield_llm_provider,
        llm_mode=settings.shield_llm_mode,
        redaction_mode=settings.shield_redaction_mode,
    )
    yield
    log.info("api_stopping")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="SHIELD by Kentro - API",
        version=__version__,
        docs_url="/docs" if not settings.is_production() else None,
        redoc_url=None,
        openapi_url="/openapi.json" if not settings.is_production() else None,
        lifespan=_lifespan,
    )

    app.add_middleware(CorrelationIdMiddleware)
    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(oidc.router)
    app.include_router(intake.router)
    app.include_router(artifacts.router)
    app.include_router(admin.router)
    app.include_router(notifications.router)
    app.include_router(tech_debt.router)
    app.include_router(csf.router)
    app.include_router(zt.router)
    app.include_router(attack.router)
    app.include_router(messages.router)
    app.include_router(risk.router)
    app.include_router(clients.router)
    app.include_router(ai_preview.router)

    return app


app = create_app()
