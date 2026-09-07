"""OrderKoi API — order tracking for F-commerce sellers."""

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
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
    """Boot checks only — the schema is owned by Alembic migrations.

    To set up (or update) a database:
        cd backend && alembic upgrade head
    (Alembic reads DATABASE_URL / PG_* from .env — same source of
    truth as the app.)
    """
    _validate_production_config()
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


# Browser-hardening headers on every response. CSP is deliberately NOT
# set here: this service is a JSON API — the browser-facing CSP belongs
# to whatever serves the frontend (nginx/Caddy at deploy time).
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    for header, value in SECURITY_HEADERS.items():
        response.headers[header] = value
    return response


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


@app.get("/ready", tags=["system"])
def readiness_check(db: Session = Depends(get_db)) -> JSONResponse:
    """Readiness probe — actually touches the database.

    /health says "the process is up"; /ready says "and it can serve
    requests" — a load balancer or deploy check should use this one,
    because a DB outage makes the app up-but-useless.
    """
    try:
        db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 — any DB failure means not ready
        logger.exception("Readiness check failed — database unreachable")
        return JSONResponse(
            status_code=503,
            content={"status": "not ready", "reason": "database unavailable"},
        )
    return JSONResponse(status_code=200, content={"status": "ready"})
