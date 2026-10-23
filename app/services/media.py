"""Bystander photo handling: validation, EXIF stripping, encryption, retention.

Every uploaded image is decoded and **re-encoded** to JPEG. That guarantees:

* the stored file is a real image (no polyglot/malicious payloads),
* EXIF metadata (GPS, device serials, owner names) is stripped,
* size is bounded (long edge capped at ``MEDIA_MAX_DIMENSION``).

The re-encoded bytes are then Fernet-encrypted in the database via the
``EncryptedBytes`` column type. ``purge_expired`` deletes photos once their
30-day retention period ends.
"""

from __future__ import annotations

import hashlib
import io
import logging
from datetime import timedelta

from PIL import Image, ImageOps, UnidentifiedImageError

from ..extensions import db
from ..models.base import utcnow
from ..models.media import Media

log = logging.getLogger(__name__)

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
Image.MAX_IMAGE_PIXELS = 40_000_000  # decompression-bomb guard


class MediaError(ValueError):
    """User-facing upload problem."""


def process_image(raw: bytes, max_bytes: int, max_dimension: int) -> tuple[bytes, int, int]:
    """Validate and sanitise an uploaded image. Returns ``(jpeg_bytes, w, h)``."""
    if not raw:
        raise MediaError("The photo was empty.")
    if len(raw) > max_bytes:
        raise MediaError(f"Photo too large (max {max_bytes // (1024 * 1024)} MB).")
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            fmt = probe.format
            probe.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError) as exc:
        raise MediaError("That file is not a valid image.") from exc
    if fmt not in ALLOWED_FORMATS:
        raise MediaError("Only JPEG, PNG or WEBP photos are accepted.")
    try:
        with Image.open(io.BytesIO(raw)) as img:
            img = ImageOps.exif_transpose(img)   # honour orientation, then drop EXIF
            img = img.convert("RGB")
            img.thumbnail((max_dimension, max_dimension))
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=82, optimize=True)  # no exif= -> stripped
            return out.getvalue(), img.width, img.height
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise MediaError("The photo could not be processed.") from exc


def store_photo(emergency, raw: bytes, config) -> Media:
    """Sanitise, encrypt and attach a photo to ``emergency`` (caller commits)."""
    live = emergency.live_media()
    if len(live) >= config["MEDIA_MAX_PER_EMERGENCY"]:
        raise MediaError(f"Maximum of {config['MEDIA_MAX_PER_EMERGENCY']} photos per report.")
    jpeg, width, height = process_image(raw, config["MEDIA_MAX_BYTES"], config["MEDIA_MAX_DIMENSION"])
    now = utcnow()
    media = Media(
        emergency=emergency,
        data=jpeg,
        mime_type="image/jpeg",
        size_bytes=len(jpeg),
        width=width,
        height=height,
        sha256=hashlib.sha256(jpeg).hexdigest(),
        consent_given=True,
        created_at=now,
        expires_at=now + timedelta(days=config["MEDIA_RETENTION_DAYS"]),
    )
    db.session.add(media)
    return media


def purge_expired(now=None) -> int:
    """Permanently delete photos past their retention date. Returns count."""
    now = now or utcnow()
    expired = Media.query.filter(Media.expires_at <= now).all()
    for item in expired:
        db.session.delete(item)
    if expired:
        db.session.commit()
        log.info("Media retention: purged %d expired photo(s)", len(expired))
    return len(expired)


def start_purge_loop(app, socketio) -> None:
    """Run ``purge_expired`` periodically in a background green thread."""
    interval = max(60, int(app.config["MEDIA_PURGE_INTERVAL_SECONDS"]))

    def _loop():
        while True:
            try:
                with app.app_context():
                    purge_expired()
            except Exception:  # noqa: BLE001 - never let the loop die
                log.exception("Media purge failed; will retry")
                try:
                    with app.app_context():
                        db.session.rollback()
                except Exception:  # noqa: BLE001
                    pass
            socketio.sleep(interval)

    socketio.start_background_task(_loop)
    log.info("Media retention loop started (every %ss, keep %s days)",
             interval, app.config["MEDIA_RETENTION_DAYS"])
