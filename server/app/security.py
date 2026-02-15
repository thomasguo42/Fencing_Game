from __future__ import annotations

from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from server.app.config import settings


_password_hasher = PasswordHasher()
_serializer = URLSafeTimedSerializer(settings.secret_key, salt="game-session")


def hash_password(raw_password: str) -> str:
    return _password_hasher.hash(raw_password)


def verify_password(raw_password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, raw_password)
    except VerifyMismatchError:
        return False


def encode_session(payload: dict[str, Any]) -> str:
    return _serializer.dumps(payload)


def decode_session(token: str) -> dict[str, Any] | None:
    try:
        raw = _serializer.loads(token, max_age=settings.session_max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(raw, dict):
        return None
    return raw
