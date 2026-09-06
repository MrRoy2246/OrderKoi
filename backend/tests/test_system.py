"""System-level tests: security headers and health/readiness probes."""

EXPECTED_SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "strict-origin-when-cross-origin",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
}


def test_security_headers_on_every_response(client):
    response = client.get("/health")
    assert response.status_code == 200
    for header, value in EXPECTED_SECURITY_HEADERS.items():
        assert response.headers.get(header) == value, f"missing/wrong {header}"


def test_security_headers_on_api_responses_too(client, auth_headers):
    """The headers must ride on authenticated API responses as well,
    not just the system endpoints."""
    response = client.get("/auth/me", headers=auth_headers)
    assert response.status_code == 200
    for header in EXPECTED_SECURITY_HEADERS:
        assert response.headers.get(header) is not None


def test_ready_returns_200_when_db_reachable(client):
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_returns_503_when_db_unreachable(client, monkeypatch):
    """A dead database must flip /ready to 503 — that's the whole point
    of a readiness probe that actually touches the DB."""
    from sqlalchemy import text as sql_text

    def broken_execute(self, *_args, **_kwargs):
        raise RuntimeError("simulated database outage")

    # Break Session.execute for every session the app creates
    monkeypatch.setattr("sqlalchemy.orm.Session.execute", broken_execute)

    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "not ready"
