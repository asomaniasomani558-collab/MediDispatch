"""Development entry point.

    python run.py                 # http://localhost:5000 (SQLite, auto-creates tables)

Production uses ``wsgi.py`` under Gunicorn + Eventlet (see docker-compose.yml).
"""

import os

from app import create_app, start_background_jobs
from app.extensions import db, socketio

app = create_app(os.environ.get("APP_ENV", "development"))

if __name__ == "__main__":
    with app.app_context():
        db.create_all()  # convenience for local SQLite; production uses `flask init-db`
    start_background_jobs(app)
    socketio.run(
        app,
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=app.config.get("DEBUG", False),
        use_reloader=False,
        allow_unsafe_werkzeug=True,  # dev server only
    )
