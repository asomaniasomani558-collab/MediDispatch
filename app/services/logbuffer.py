"""Logging setup: console + rotating file + in-memory ring buffer.

The ring buffer feeds the admin "System Logs" panel without needing shell
access to the server. Patient identifiers are never logged by design.
"""

from __future__ import annotations

import logging
import os
import threading
from collections import deque
from logging.handlers import RotatingFileHandler

FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


class RingBufferHandler(logging.Handler):
    def __init__(self, capacity: int = 500) -> None:
        super().__init__()
        self.records: deque = deque(maxlen=capacity)
        self._buf_lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "time": record.created,
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage()[:1000],
            }
        except Exception:  # noqa: BLE001
            return
        with self._buf_lock:
            self.records.append(entry)

    def recent(self, limit: int = 200, min_level: str = "DEBUG") -> list[dict]:
        threshold = logging.getLevelName(min_level)
        threshold = threshold if isinstance(threshold, int) else 0
        with self._buf_lock:
            items = list(self.records)
        items = [r for r in items if logging.getLevelName(r["level"]) >= threshold]
        return list(reversed(items[-limit:]))


ring_buffer = RingBufferHandler()


def configure_logging(app) -> None:
    level = getattr(logging, str(app.config.get("LOG_LEVEL", "INFO")).upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)
    formatter = logging.Formatter(FORMAT)

    if not any(isinstance(h, RingBufferHandler) for h in root.handlers):
        ring_buffer.setLevel(logging.INFO)
        root.addHandler(ring_buffer)
    if not any(getattr(h, "_medidispatch_console", False) for h in root.handlers):
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        console._medidispatch_console = True  # type: ignore[attr-defined]
        root.addHandler(console)
    if app.config.get("LOG_TO_FILE") and not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        try:
            os.makedirs(app.config["LOG_DIR"], exist_ok=True)
            file_handler = RotatingFileHandler(
                os.path.join(app.config["LOG_DIR"], "medidispatch.log"),
                maxBytes=5 * 1024 * 1024, backupCount=10,
            )
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)
        except OSError as exc:
            root.warning("File logging disabled: %s", exc)
    for noisy in ("engineio", "socketio", "werkzeug", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
