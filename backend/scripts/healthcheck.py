"""Container healthcheck — exits 0 when the API can serve requests.

Used by the `backend` service healthcheck in docker-compose.yml (the
slim Python image ships no curl/wget, so the probe is Python).

Hits /ready rather than /health on purpose: /health only proves the
process is up, while /ready executes a real `SELECT 1` against
Postgres. That is the difference between "gunicorn is running" and
"the site actually works" — a backend that is up but has lost its
database must be reported unhealthy so it gets restarted and so Caddy
never routes to it.

    python -m scripts.healthcheck
    HEALTHCHECK_URL=http://127.0.0.1:8000/ready python -m scripts.healthcheck

Exit codes: 0 healthy, 1 unhealthy (also used as the Docker health
status).
"""

import os
import sys
import urllib.error
import urllib.request

DEFAULT_URL = "http://127.0.0.1:8000/ready"
TIMEOUT_SECONDS = 5


def main() -> int:
    url = os.environ.get("HEALTHCHECK_URL", DEFAULT_URL)
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:
            if 200 <= response.status < 300:
                return 0
            print(f"unhealthy: {url} returned HTTP {response.status}", file=sys.stderr)
            return 1
    except urllib.error.HTTPError as exc:
        # /ready answers 503 when the database is unreachable — the
        # expected "up but not usable" signal.
        print(f"unhealthy: {url} returned HTTP {exc.code}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 — any failure means not serving
        print(f"unhealthy: could not reach {url}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
