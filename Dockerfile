# MediDispatch GH - application image (Gunicorn + Eventlet)
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_ENV=production \
    LOG_DIR=/app/logs

WORKDIR /app

# libpq for psycopg2 at runtime; curl for the container health check.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Run as an unprivileged user.
RUN useradd --create-home --uid 10001 medidispatch \
    && mkdir -p /app/logs /app/instance \
    && chown -R medidispatch:medidispatch /app/logs /app/instance
USER medidispatch

EXPOSE 8000

HEALTHCHECK --interval=20s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

# One eventlet worker per container (Socket.IO requirement); scale with replicas.
CMD ["gunicorn", "--worker-class", "eventlet", "--workers", "1", \
     "--bind", "0.0.0.0:8000", "--timeout", "60", "--graceful-timeout", "30", \
     "--access-logfile", "-", "--error-logfile", "-", "wsgi:app"]
