"""OrderKoi API — order tracking for F-commerce sellers."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import Base, engine
from app.rate_limit import enforce_rate_limits
from app.routes import admin, auth, orders, public, tracking

settings = get_settings()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("orderkoi")


def _validate_production_config() -> None:
    """Refuse to run in production with a default/weak secret key.

    If the app ever starts with the publicly-known default, every JWT
    it signs is forgeable by anyone who has read the source — total
    account takeover, including admin. Better to crash at boot than
    run insecure.
    """
    if settings.environment != "production":
        return
    if settings.secret_key == "dev-only-change-me" or len(settings.secret_key) < 32:
        raise RuntimeError(
            "REFUSING TO START: SECRET_KEY is missing, default, or too short "
            "for production. Generate a long random value with "
            "`python -c \"import secrets; print(secrets.token_hex(32))\"` "
            "and set it in backend/.env."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create database tables on startup (dev convenience; Alembic
    migrations replace this in Phase 8)."""
    _validate_production_config()
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.api_version,
    description=(
        "Order tracking platform for small online sellers. "
        "Sellers manage orders; customers track them via a public link."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Brute-force and abuse protection (skipped for the test suite)."""
    if settings.environment != "test":
        limited = enforce_rate_limits(request)
        if limited is not None:
            return limited
    return await call_next(request)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Never leak stack traces or internals to clients — log instead."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Please try again later."},
    )


app.include_router(auth.router)
app.include_router(orders.router)
app.include_router(tracking.router)
app.include_router(admin.router)
app.include_router(public.router)


@app.get("/health", tags=["system"])
def health_check() -> dict:
    """Liveness probe — the frontend (and later, monitoring) calls this."""
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.environment,
    }
