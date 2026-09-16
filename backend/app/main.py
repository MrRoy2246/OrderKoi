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
from app.deps import SUSPENDED_HEADER
from app.rate_limit import enforce_rate_limits
from app.routes import admin, auth, orders, public, tracking

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("orderkoi")


def _validate_production_config() -> None:
    """Refuse to boot a production deployment that is misconfigured.

    Every check here is fail-closed: crash at startup rather than run
    in a state that silently loses accounts, emails, or security.
    Development and test are deliberately exempt so `alembic upgrade
    head`, the test suite, and local work keep functioning.

    All problems are collected and reported together — fixing one
    misconfiguration only to hit the next on the following restart is
    a miserable way to deploy.
    """
    if settings.environment != "production":
        return

    problems: list[str] = []

    # A forgeable JWT secret is total account takeover, including
    # admin: anyone who has read the source can mint a valid token.
    if settings.secret_key == "dev-only-change-me" or len(settings.secret_key) < 32:
        problems.append(
            "SECRET_KEY is missing, default, or too short — every JWT "
            "would be forgeable. Generate one with "
            "`python -c \"import secrets; print(secrets.token_hex(32))\"`."
        )

    # Without SMTP, signup is a dead end: login requires a verified
    # email, and verification links are only printed to the log. Every
    # new account would be permanently unreachable, so this is not a
    # "warning" — the deployment cannot function.
    #
    # uses_console_email rather than `not smtp_host` so an explicit
    # EMAIL_BACKEND=console is caught too: setting a real SMTP_HOST
    # while leaving the backend on console is the more confusing of
    # the two mistakes, and it passes an smtp_host check silently.
    if settings.uses_console_email:
        problems.append(
            "email is on the console backend (EMAIL_BACKEND=console, or "
            "SMTP_HOST empty) — verification and password-reset emails "
            "would only be written to the log, so no user could ever "
            "sign in or recover an account."
        )

    # Reset/verification links are built from this. Pointing at
    # localhost means every emailed link is dead on arrival.
    if "localhost" in settings.frontend_url or "127.0.0.1" in settings.frontend_url:
        problems.append(
            f"FRONTEND_URL is still {settings.frontend_url!r} — every "
            "password-reset and verification link would be unusable."
        )

    if problems:
        raise RuntimeError(
            "REFUSING TO START — production configuration is invalid:\n  - "
            + "\n  - ".join(problems)
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
    # Off in production unless ENABLE_API_DOCS=true — /docs and
    # /openapi.json are unauthenticated and enumerate every admin
    # route, which is a map of what to attack.
    docs_url="/docs" if settings.api_docs_enabled else None,
    redoc_url="/redoc" if settings.api_docs_enabled else None,
    openapi_url="/openapi.json" if settings.api_docs_enabled else None,
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


# CORS is added LAST so it sits OUTERMOST in the stack (Starlette
# wraps in reverse order of registration). That position is the whole
# point: the rate limiter below short-circuits with its own 429
# response, and a middleware that returns without calling
# `call_next` only gets headers from layers outside it. Added
# anywhere else, a rate-limited browser request came back with no
# Access-Control-Allow-Origin and the frontend reported a CORS error
# instead of "you're going too fast" — so the user never saw the real
# message and the client could not read the Retry-After.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Custom response headers are invisible to browser JS unless they
    # are named here. The frontend reads the suspension marker (see
    # app/deps.py) to sign a cut-off seller out with a clear message
    # rather than leaving them in a half-working session — without this
    # line that header arrives as null and the check silently never
    # fires.
    expose_headers=[SUSPENDED_HEADER],
)


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
