"""Password hashing and JWT issuance/verification.

Uses the ``bcrypt`` package directly rather than passlib's CryptContext:
passlib 1.7.4 (last release, 2020) reads ``bcrypt.__about__.__version__`` to
detect the backend version, which the ``bcrypt`` package removed in 4.1 —
that combination breaks hashing outright (verified in
backend/scripts/check_agent_compat.py). Calling ``bcrypt`` directly avoids
depending on an unmaintained compatibility shim.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import bcrypt
from jose import JWTError, jwt

from thesisguard_backend.config import get_settings

_BCRYPT_MAX_BYTES = 72  # bcrypt's hard algorithm limit; longer inputs raise ValueError.


def hash_password(raw_password: str) -> str:
    truncated = raw_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(truncated, bcrypt.gensalt()).decode("utf-8")


def verify_password(raw_password: str, password_hash: str) -> bool:
    truncated = raw_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.checkpw(truncated, password_hash.encode("utf-8"))


def create_access_token(*, subject: str) -> str:
    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": subject, "exp": expires_at}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str | None:
    """Return the user id (sub) if the token is valid, else None."""

    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
    return payload.get("sub")
