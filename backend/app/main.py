"""FastAPI application entrypoint."""

from fastapi import FastAPI

from app.api.v1.router import api_v1_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
    )
    app.include_router(api_v1_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()

