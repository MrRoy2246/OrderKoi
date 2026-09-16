"""Settings-level validation — the guards that run before anything else.

These construct `Settings` directly rather than importing the app: a
rejected configuration must fail at construction time, which is what
makes a bad .env a boot crash instead of a runtime surprise.
"""

import pytest
from pydantic import ValidationError

from app.config import Settings

# Satisfies the "no database configured" validator so each case below
# tests exactly one thing.
DB_URL = "postgresql+psycopg://u:p@localhost:5432/orderkoi"


def _settings(**overrides) -> Settings:
    return Settings(database_url=DB_URL, **overrides)


# ---------- environment ----------

def test_environment_typo_fails_loudly():
    """`ENVIRONMENT=prod` used to disable every production safety check
    while looking correct in .env — the most dangerous typo available."""
    with pytest.raises(ValidationError):
        _settings(environment="prod")


def test_environment_accepts_the_three_real_values():
    for value in ("development", "test", "production"):
        assert _settings(environment=value).environment == value


# ---------- CORS ----------

def test_cors_wildcard_is_rejected():
    """With allow_credentials=True a wildcard origin would let any site
    on the internet call the API as a signed-in user."""
    with pytest.raises(ValidationError, match="must not contain"):
        _settings(cors_origins=["*"])


def test_cors_wildcard_mixed_with_real_origins_is_rejected():
    """A list that merely contains "*" is just as dangerous — and is
    the shape a rushed edit actually produces."""
    with pytest.raises(ValidationError, match="must not contain"):
        _settings(cors_origins=["https://orderkoi.example.com", "*"])


def test_empty_cors_is_rejected_in_production():
    """Nobody could reach the API — a silent total outage."""
    with pytest.raises(ValidationError, match="CORS_ORIGINS is empty"):
        _settings(environment="production", cors_origins=[])


def test_empty_cors_is_allowed_outside_production():
    """Local/server-to-server tooling may legitimately want no browser
    origins allowed."""
    assert _settings(cors_origins=[]).cors_origins == []


# ---------- API docs ----------

def test_api_docs_are_off_in_production_by_default():
    """/docs and /openapi.json are unauthenticated and enumerate every
    admin route — a map of what to attack."""
    assert _settings(environment="production").api_docs_enabled is False


def test_api_docs_are_on_in_development_and_test():
    assert _settings(environment="development").api_docs_enabled is True
    assert _settings(environment="test").api_docs_enabled is True


def test_api_docs_can_be_forced_either_way():
    assert (
        _settings(environment="production", enable_api_docs=True).api_docs_enabled
        is True
    )
    assert (
        _settings(environment="development", enable_api_docs=False).api_docs_enabled
        is False
    )


# ---------- email backend ----------
#
# Every case pins email_backend explicitly: conftest sets
# EMAIL_BACKEND=console process-wide for the suite (so tests never touch
# the network), and that would otherwise leak into "auto" here and make
# these assertions pass or fail for the wrong reason.

def test_auto_uses_console_only_when_smtp_host_is_empty():
    """'auto' is the development default: no SMTP_HOST means mail is
    logged, never sent."""
    assert _settings(email_backend="auto", smtp_host="").uses_console_email is True
    assert (
        _settings(email_backend="auto", smtp_host="smtp.example.com").uses_console_email
        is False
    )


def test_console_wins_over_a_configured_smtp_host():
    """The whole reason EMAIL_BACKEND exists: with env_ignore_empty, an
    empty SMTP_HOST means 'unset' and .env's real credentials win. The
    test suite needs an explicit, non-empty way to stay offline — this
    is it. It must beat a populated .env, which is what this asserts."""
    s = _settings(
        email_backend="console",
        smtp_host="smtp.gmail.com",
        smtp_username="someone@gmail.com",
        smtp_password="app-password",
    )
    assert s.uses_console_email is True


def test_smtp_sends_even_with_no_host_configured():
    """EMAIL_BACKEND=smtp must NOT quietly fall back to console: an
    operator who chose smtp deserves a loud delivery failure, not mail
    that silently never leaves the process."""
    assert (
        _settings(email_backend="smtp", smtp_host="").uses_console_email is False
    )


def test_email_backend_rejects_an_unknown_value():
    """A typo like EMAIL_BACKEND=consol would otherwise fall through to
    'auto' and start sending live mail from the test suite."""
    with pytest.raises(ValidationError):
        _settings(email_backend="consol")
