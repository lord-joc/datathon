"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1 import api_router
from app.core.config import Settings, get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.rate_limit import Rule


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="ProstorIQ API",
        version=__version__,
        # Interactive docs only outside production; the contract lives in docs/contracts.
        docs_url=None if settings.is_production else "/api/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/api/openapi.json",
    )

    public = settings.public_rate_limit_per_minute
    heavy = settings.heavy_rate_limit_per_minute
    rules = (
        (Rule("public", public, 2 * public), Rule("heavy", heavy, heavy))
        if settings.rate_limit_enabled
        else None
    )
    app.add_middleware(
        RequestContextMiddleware, max_body_bytes=settings.max_json_body_bytes, rules=rules
    )
    if not settings.is_production:
        # Production is same-origin behind Caddy, so CORS is not enabled there at all.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.allowed_origins,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "X-Ranking-Token", "X-Request-ID"],
            allow_credentials=False,
        )

    install_error_handlers(app)
    app.include_router(api_router)
    if settings.ai_preload:
        from app.api.v1.ai import preload

        preload()
    return app


app = create_app()
