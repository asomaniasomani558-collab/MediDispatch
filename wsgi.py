"""Production WSGI entry point for Gunicorn with the Eventlet worker.

    gunicorn --worker-class eventlet -w 1 --bind 0.0.0.0:8000 wsgi:app

Monkey-patching MUST happen before anything else is imported so that
sockets, threads and the PostgreSQL driver cooperate with Eventlet.
One worker per container: Socket.IO sessions are sticky to a process;
scale horizontally with more containers behind Nginx + the Redis queue.
"""

import eventlet

eventlet.monkey_patch()

try:  # make psycopg2 cooperative so DB calls don't block the event loop
    from psycogreen.eventlet import patch_psycopg

    patch_psycopg()
except ImportError:  # pragma: no cover
    pass

import os  # noqa: E402

from app import create_app, start_background_jobs  # noqa: E402

app = create_app(os.environ.get("APP_ENV", "production"))
start_background_jobs(app)
