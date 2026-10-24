"""Main FastAPI application entrypoint for Astrology WhatsApp AI Platform API."""

import os
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from api.config import get_settings
from api.db.session import get_async_sessionmaker
from api.services.scheduler import scheduler_daemon
from api.security.encryption import EncryptionError, DecryptionError
from api.routers.health import router as health_router
from api.routers.auth import router as auth_router
from api.routers.admin_users import router as admin_users_router
from api.routers.privacy import router as privacy_router
from api.routers.webhook_whatsapp import router as whatsapp_router
from api.routers.schedules import router as schedules_router
from api.routers.admin_dashboard import router as admin_dashboard_router

logger = logging.getLogger("api.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle handler."""
    # Validate application configuration fail-closed on boot
    try:
        settings = get_settings()
        logger.info(
            "Application booting in '%s' environment (log_level=%s)",
            settings.ENVIRONMENT,
            settings.LOG_LEVEL,
        )
        if settings.ENABLE_BACKGROUND_SCHEDULER:
            session_factory = get_async_sessionmaker()
            scheduler_daemon.start(session_factory)
    except Exception as exc:
        logger.critical("Fatal configuration validation failure during startup: %s", exc)
        raise

    yield

    if scheduler_daemon.is_running:
        await scheduler_daemon.stop()
    logger.info("Application shutting down cleanly.")


def create_app() -> FastAPI:
    """FastAPI application factory."""
    settings = get_settings()

    app = FastAPI(
        title="Astrology WhatsApp AI Platform API",
        version="0.2.0",
        description="Core persistence, privacy lifecycle, and admin authentication backend.",
        docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
        redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
        openapi_url="/openapi.json" if settings.ENVIRONMENT != "production" else None,
        lifespan=lifespan,
    )

    # Cross-Origin Resource Sharing (CORS) - restricted defaults
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.ENVIRONMENT == "development" else [],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # Cryptographic exception handlers — fail-closed, never leak keys, nonces, or ciphertexts
    @app.exception_handler(EncryptionError)
    async def encryption_error_handler(request: Request, exc: EncryptionError):
        logger.error("Cryptographic encryption failure on route '%s': %s", request.url.path, exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "Cryptographic failure",
                "message": "An internal encryption error occurred while protecting sensitive data.",
            },
        )

    @app.exception_handler(DecryptionError)
    async def decryption_error_handler(request: Request, exc: DecryptionError):
        logger.error("Cryptographic decryption/integrity failure on route '%s': %s", request.url.path, exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "Decryption failure",
                "message": "Data could not be decrypted or authentication tag verification failed.",
            },
        )

    # Register API routers
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(admin_users_router)
    app.include_router(privacy_router)
    app.include_router(whatsapp_router)
    app.include_router(schedules_router)
    app.include_router(admin_dashboard_router)

    # Mount lightweight Internal Admin Dashboard
    static_admin_dir = os.path.join(os.path.dirname(__file__), "static", "admin")
    if os.path.exists(static_admin_dir):
        app.mount("/admin/assets", StaticFiles(directory=static_admin_dir), name="admin_assets")

        @app.get("/admin", include_in_schema=False)
        @app.get("/admin/", include_in_schema=False)
        async def serve_admin_dashboard():
            response = FileResponse(os.path.join(static_admin_dir, "index.html"))
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            return response

    return app


app = create_app()
