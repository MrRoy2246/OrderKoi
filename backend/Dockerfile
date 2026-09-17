# OrderKoi API — production image.
#
# Runs gunicorn with exactly ONE uvicorn worker: the rate limiter and
# login throttle are in-memory, per-process — a second worker would
# give every visitor two separate buckets (and the buckets would be
# half as effective). Redis-backed limiting is the scale-out upgrade;
# until then one worker is a correctness requirement, not a choice.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Behind Caddy on the compose network. uvicorn (via gunicorn's
    # UvicornWorker) reads this env var: X-Forwarded-For from the proxy
    # becomes request.client.host, which is what the rate limiter keys
    # on. The backend port is never published to the internet (only
    # Caddy / loopback can reach it), so trusting the whole network is
    # safe here.
    FORWARDED_ALLOW_IPS=*

WORKDIR /app

# Dependencies first — this layer is cached across code changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App + migrations (entrypoint runs `alembic upgrade head` before the
# server starts) + ops scripts (`python -m scripts.create_admin` for
# bootstrapping the admin account on a fresh database).
COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app
COPY scripts ./scripts

# Don't run as root
RUN useradd --create-home orderkoi && chown -R orderkoi:orderkoi /app
USER orderkoi

EXPOSE 8000

# Single worker (see comment at the top). Logs to stdout so
# `docker logs` / log drivers see them.
CMD ["gunicorn", "app.main:app", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "-w", "1", \
     "-b", "0.0.0.0:8000", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
