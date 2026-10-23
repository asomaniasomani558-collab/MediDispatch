"""Field-level encryption at rest.

Patient vitals, phone numbers, names, locations and photos are stored as
Fernet tokens (AES-128-CBC + HMAC-SHA256, authenticated). ``MultiFernet`` lets
us rotate keys: the first key in ``FIELD_ENCRYPTION_KEYS`` encrypts new data,
every listed key can decrypt older rows.

The SQLAlchemy ``TypeDecorator`` classes below make encryption transparent:
models declare ``EncryptedText`` / ``EncryptedJSON`` / ``EncryptedBytes``
columns and application code reads and writes plain Python values.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from typing import Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy import LargeBinary, Text
from sqlalchemy.types import TypeDecorator

log = logging.getLogger(__name__)


class EncryptionError(RuntimeError):
    """Raised when data cannot be encrypted or decrypted."""


class _KeyRing:
    """Process-wide holder for the active ``MultiFernet`` instance."""

    def __init__(self) -> None:
        self._fernet: MultiFernet | None = None

    def configure(self, keys_csv: str, secret_key: str = "", allow_derived: bool = False) -> None:
        keys = [k.strip() for k in (keys_csv or "").split(",") if k.strip()]
        if not keys:
            if not allow_derived:
                raise EncryptionError("FIELD_ENCRYPTION_KEYS is not configured")
            # Development convenience only: derive a stable key from SECRET_KEY
            # so a fresh checkout runs. Production refuses this path.
            digest = hashlib.sha256(("medidispatch-dev:" + secret_key).encode()).digest()
            keys = [base64.urlsafe_b64encode(digest).decode()]
            log.warning("FIELD_ENCRYPTION_KEYS not set - using a key derived from SECRET_KEY (dev only)")
        try:
            self._fernet = MultiFernet([Fernet(k.encode()) for k in keys])
        except (ValueError, TypeError) as exc:
            raise EncryptionError(f"Invalid Fernet key in FIELD_ENCRYPTION_KEYS: {exc}") from exc

    @property
    def fernet(self) -> MultiFernet:
        if self._fernet is None:
            raise EncryptionError("Encryption key ring has not been configured")
        return self._fernet


keyring = _KeyRing()


def init_app(app) -> None:
    keyring.configure(
        app.config.get("FIELD_ENCRYPTION_KEYS", ""),
        app.config.get("SECRET_KEY", ""),
        allow_derived=not app.config.get("ENV_NAME") == "production",
    )


def encrypt_bytes(data: bytes) -> bytes:
    return keyring.fernet.encrypt(data)


def decrypt_bytes(token: bytes) -> bytes:
    try:
        return keyring.fernet.decrypt(token)
    except InvalidToken as exc:
        raise EncryptionError("Ciphertext failed authentication (wrong key or tampered data)") from exc


def encrypt_str(value: str) -> str:
    return encrypt_bytes(value.encode("utf-8")).decode("ascii")


def decrypt_str(token: str) -> str:
    return decrypt_bytes(token.encode("ascii")).decode("utf-8")


def generate_key() -> str:
    """Return a fresh Fernet key (used by ``flask generate-key``)."""
    return Fernet.generate_key().decode()


class EncryptedText(TypeDecorator):
    """A ``str`` column stored as a Fernet token."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect) -> str | None:
        if value is None:
            return None
        return encrypt_str(str(value))

    def process_result_value(self, value: Any, dialect) -> str | None:
        if value is None:
            return None
        try:
            return decrypt_str(value)
        except EncryptionError:
            # Never crash a dispatcher's screen over one bad row; surface it.
            log.error("Could not decrypt an EncryptedText value - key mismatch?")
            return "[unreadable]"


class EncryptedJSON(TypeDecorator):
    """A JSON-serialisable value (dict / list) stored as a Fernet token."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect) -> str | None:
        if value is None:
            return None
        return encrypt_str(json.dumps(value, separators=(",", ":"), sort_keys=True))

    def process_result_value(self, value: Any, dialect) -> Any:
        if value is None:
            return None
        try:
            return json.loads(decrypt_str(value))
        except (EncryptionError, ValueError):
            log.error("Could not decrypt an EncryptedJSON value - key mismatch?")
            return None


class EncryptedBytes(TypeDecorator):
    """Binary data (photos) stored as a Fernet token."""

    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value: Any, dialect) -> bytes | None:
        if value is None:
            return None
        return encrypt_bytes(bytes(value))

    def process_result_value(self, value: Any, dialect) -> bytes | None:
        if value is None:
            return None
        try:
            return decrypt_bytes(bytes(value))
        except EncryptionError:
            log.error("Could not decrypt an EncryptedBytes value - key mismatch?")
            return None
